"""Continuous Market Analyst — multi-TF AI reasoning over live data.

Polls MT5 for OHLCV across configurable timeframes, computes all indicators
(SMC, OB/FVG, NWE, TPO, RSI, MACD, etc.) using the Python indicator engine,
then sends the structured data to Claude for a trading opinion.

The analyst runs as a background asyncio task, producing opinions at a
configurable interval (default: on M5 bar close).
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

from agent.ai_service import AIService
from agent.backtest.indicators import IndicatorEngine
from agent.bridge import ZMQBridge
from agent.models.market import Bar


# ── Configuration ────────────────────────────────────────────────────

@dataclass
class AnalystIndicator:
    """An indicator to compute on a specific timeframe."""
    id: str              # e.g. "h4_smc"
    name: str            # e.g. "SMC_Structure"
    timeframe: str       # e.g. "H4"
    params: dict = field(default_factory=dict)


@dataclass
class AnalystConfig:
    """Configuration for the continuous analyst."""
    symbol: str = "XAUUSD"
    timeframes: list[str] = field(default_factory=lambda: ["M5", "M15", "H1", "H4", "D1"])
    bar_count: int = 200  # bars to fetch per TF
    interval_seconds: int = 300  # default: every 5 min (M5 close)
    model: str = "sonnet"  # AI model to use (haiku for cost saving, sonnet for quality)
    max_history: int = 5  # keep last N opinions for context
    indicators: list[AnalystIndicator] = field(default_factory=list)

    def __post_init__(self):
        if not self.indicators:
            self.indicators = self._default_indicators()

    def _default_indicators(self) -> list[AnalystIndicator]:
        """Default indicator set across all timeframes."""
        indicators = []
        for tf in self.timeframes:
            tf_lower = tf.lower()
            indicators.extend([
                AnalystIndicator(f"{tf_lower}_smc", "SMC_Structure", tf, {"swing_len": 10}),
                AnalystIndicator(f"{tf_lower}_ob_fvg", "OB_FVG", tf, {}),
                AnalystIndicator(f"{tf_lower}_nwe", "NW_Envelope", tf, {"h": 8, "alpha": 8, "x_0": 25}),
                AnalystIndicator(f"{tf_lower}_tpo", "TPO", tf, {"lookback": 50, "num_bins": 24, "value_area_pct": 70.0}),
                AnalystIndicator(f"{tf_lower}_rsi", "RSI", tf, {"period": 14}),
                AnalystIndicator(f"{tf_lower}_macd", "MACD", tf, {"fast_ema": 12, "slow_ema": 26, "signal": 9}),
                AnalystIndicator(f"{tf_lower}_ema50", "EMA", tf, {"period": 50}),
                AnalystIndicator(f"{tf_lower}_ema200", "EMA", tf, {"period": 200}),
                AnalystIndicator(f"{tf_lower}_atr", "ATR", tf, {"period": 14}),
                AnalystIndicator(f"{tf_lower}_stoch", "Stochastic", tf, {"k_period": 5, "d_period": 3, "slowing": 3}),
                AnalystIndicator(f"{tf_lower}_bb", "Bollinger", tf, {"period": 20, "deviation": 2.0}),
                AnalystIndicator(f"{tf_lower}_adx", "ADX", tf, {"period": 14}),
            ])
        return indicators


# ── Opinion Model ────────────────────────────────────────────────────

@dataclass
class AnalystOpinion:
    """A single analysis opinion from the AI."""
    timestamp: datetime
    symbol: str
    current_price: float
    raw_response: dict  # full JSON from AI
    bias: str = "neutral"
    confidence: float = 0.0
    alignment: str = ""
    trade_ideas: list[dict] = field(default_factory=list)
    changes_from_last: str = ""
    computation_ms: int = 0
    ai_model: str = ""
    usage: dict = field(default_factory=dict)


# ── Core Analyst ─────────────────────────────────────────────────────

class ContinuousAnalyst:
    """Runs a background loop that continuously analyzes the market."""

    def __init__(self, bridge: ZMQBridge, ai_service: AIService, config: AnalystConfig | None = None):
        self.bridge = bridge
        self.ai = ai_service
        self.config = config or AnalystConfig()
        self._task: asyncio.Task | None = None
        self._running = False
        self._opinions: list[AnalystOpinion] = []
        self._callbacks: list = []
        self._prompt = self._load_prompt()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def latest_opinion(self) -> AnalystOpinion | None:
        return self._opinions[-1] if self._opinions else None

    @property
    def opinions(self) -> list[AnalystOpinion]:
        return list(self._opinions)

    def on_opinion(self, callback):
        """Register callback for new opinions: callback(opinion)."""
        self._callbacks.append(callback)

    def update_config(self, **kwargs):
        """Update config fields dynamically."""
        for k, v in kwargs.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
        # Regenerate indicators if timeframes changed
        if "timeframes" in kwargs or "symbol" in kwargs:
            self.config.indicators = self.config._default_indicators()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self):
        """Start the continuous analysis loop."""
        if self._running:
            logger.warning("Analyst already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"Analyst started: {self.config.symbol} | "
            f"TFs: {self.config.timeframes} | "
            f"interval: {self.config.interval_seconds}s | "
            f"model: {self.config.model}"
        )

    async def stop(self):
        """Stop the analysis loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Analyst stopped")

    async def analyze_once(self) -> AnalystOpinion | None:
        """Run a single analysis cycle (callable on-demand)."""
        return await self._run_analysis()

    # ── Main Loop ────────────────────────────────────────────────────

    async def _loop(self):
        """Background loop: analyze at each interval."""
        logger.info("Analyst loop started")
        while self._running:
            try:
                opinion = await self._run_analysis()
                if opinion:
                    for cb in self._callbacks:
                        try:
                            result = cb(opinion)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"Analyst callback error: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Analyst loop error: {e}")

            # Wait for next interval
            try:
                await asyncio.sleep(self.config.interval_seconds)
            except asyncio.CancelledError:
                break

        logger.info("Analyst loop stopped")

    # ── Analysis Pipeline ────────────────────────────────────────────

    async def _run_analysis(self) -> AnalystOpinion | None:
        """Fetch data → compute indicators → send to AI → return opinion."""
        start = time.time()
        symbol = self.config.symbol

        # 1. Fetch current price
        tick = await self.bridge.get_tick(symbol)
        if not tick:
            logger.warning(f"Analyst: no tick data for {symbol}")
            return None
        current_price = (tick.bid + tick.ask) / 2

        # 2. Fetch bars for each timeframe
        bars_by_tf: dict[str, list[Bar]] = {}
        for tf in self.config.timeframes:
            bars = await self.bridge.get_bars(symbol, tf, self.config.bar_count)
            if bars:
                bars_by_tf[tf] = bars
            else:
                logger.warning(f"Analyst: no bars for {symbol}/{tf}")

        if not bars_by_tf:
            logger.warning("Analyst: no bar data available")
            return None

        # 3. Compute indicators using the Python engine
        indicator_data = self._compute_indicators(bars_by_tf)

        # 4. Build recent candle summaries per TF
        candle_data = self._build_candle_summary(bars_by_tf, current_price)

        # 5. Build the prompt payload
        payload = self._build_payload(symbol, current_price, tick, candle_data, indicator_data)

        # 6. Get previous opinions for context
        prev_context = self._build_previous_context()

        # 7. Send to AI
        try:
            opinion = await self._call_ai(symbol, current_price, payload, prev_context)
        except Exception as e:
            logger.error(f"Analyst AI call failed: {e}")
            return None

        # 8. Record timing
        opinion.computation_ms = int((time.time() - start) * 1000)

        # 9. Store and trim history
        self._opinions.append(opinion)
        if len(self._opinions) > self.config.max_history:
            self._opinions = self._opinions[-self.config.max_history:]

        logger.info(
            f"Analyst opinion: {opinion.bias} ({opinion.confidence:.0%}) | "
            f"{opinion.alignment} | {opinion.computation_ms}ms"
        )
        return opinion

    def _compute_indicators(self, bars_by_tf: dict[str, list[Bar]]) -> dict[str, dict[str, Any]]:
        """Compute all indicators across timeframes using IndicatorEngine."""
        results: dict[str, dict[str, Any]] = {}

        # Create an IndicatorEngine per timeframe
        engines: dict[str, IndicatorEngine] = {}
        for tf, bars in bars_by_tf.items():
            engines[tf] = IndicatorEngine(bars)

        for ind in self.config.indicators:
            engine = engines.get(ind.timeframe)
            if not engine:
                continue
            try:
                # Compute at the last bar (current state)
                bar_count = len(bars_by_tf[ind.timeframe])
                values = engine.compute_at(bar_count - 1, ind.name, ind.params)
                results[ind.id] = {
                    "name": ind.name,
                    "timeframe": ind.timeframe,
                    "values": self._clean_values(values),
                }
            except Exception as e:
                logger.debug(f"Analyst: indicator {ind.id} failed: {e}")

        return results

    def _clean_values(self, values: dict[str, float]) -> dict[str, float]:
        """Clean indicator values — replace NaN/inf with 0."""
        import math
        cleaned = {}
        for k, v in values.items():
            if k.startswith("_"):
                continue  # skip marker keys
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                cleaned[k] = 0.0
            else:
                cleaned[k] = round(float(v), 5) if isinstance(v, (int, float)) else v
        return cleaned

    def _build_candle_summary(
        self, bars_by_tf: dict[str, list[Bar]], current_price: float
    ) -> dict[str, dict]:
        """Build a summary of recent candles per timeframe."""
        summaries = {}
        for tf, bars in bars_by_tf.items():
            if not bars:
                continue
            recent = bars[-5:]  # last 5 candles
            candles = []
            for b in recent:
                candles.append({
                    "time": b.time.isoformat(),
                    "open": round(b.open, 2),
                    "high": round(b.high, 2),
                    "low": round(b.low, 2),
                    "close": round(b.close, 2),
                    "volume": b.volume,
                })
            # Price range context
            all_highs = [b.high for b in bars[-50:]]
            all_lows = [b.low for b in bars[-50:]]
            summaries[tf] = {
                "recent_candles": candles,
                "range_high_50": round(max(all_highs), 2) if all_highs else 0,
                "range_low_50": round(min(all_lows), 2) if all_lows else 0,
                "bar_count": len(bars),
            }
        return summaries

    def _build_payload(
        self,
        symbol: str,
        current_price: float,
        tick,
        candle_data: dict,
        indicator_data: dict,
    ) -> str:
        """Build the structured text payload for the AI prompt."""
        parts = []
        parts.append(f"## Market Data for {symbol}")
        parts.append(f"**Current Price:** {current_price:.2f} (bid: {tick.bid:.2f}, ask: {tick.ask:.2f}, spread: {tick.spread:.1f})")
        parts.append(f"**Timestamp:** {tick.timestamp.isoformat()}")

        # Group indicators by timeframe
        by_tf: dict[str, list[tuple[str, dict]]] = {}
        for ind_id, ind_data in indicator_data.items():
            tf = ind_data["timeframe"]
            if tf not in by_tf:
                by_tf[tf] = []
            by_tf[tf].append((ind_id, ind_data))

        # Output per timeframe (HTF first)
        tf_order = ["D1", "W1", "H4", "H1", "M30", "M15", "M5", "M1"]
        ordered_tfs = [tf for tf in tf_order if tf in by_tf or tf in candle_data]

        for tf in ordered_tfs:
            parts.append(f"\n### {tf} Timeframe")

            # Candle summary
            if tf in candle_data:
                cd = candle_data[tf]
                parts.append(f"50-bar range: {cd['range_low_50']} — {cd['range_high_50']}")
                parts.append(f"Last 5 candles:")
                for c in cd["recent_candles"]:
                    body = "bullish" if c["close"] > c["open"] else "bearish"
                    parts.append(f"  {c['time']}: O={c['open']} H={c['high']} L={c['low']} C={c['close']} ({body})")

            # Indicators
            if tf in by_tf:
                parts.append(f"Indicators:")
                for ind_id, ind_data in by_tf[tf]:
                    name = ind_data["name"]
                    vals = ind_data["values"]
                    vals_str = ", ".join(f"{k}={v}" for k, v in vals.items())
                    parts.append(f"  {name} ({ind_id}): {vals_str}")

        return "\n".join(parts)

    def _build_previous_context(self) -> str:
        """Build context from previous opinions for continuity."""
        if not self._opinions:
            return "No previous analysis. This is the first analysis."

        parts = ["## Previous Opinions (most recent first)"]
        for op in reversed(self._opinions[-3:]):  # last 3
            parts.append(
                f"- [{op.timestamp.strftime('%H:%M')}] "
                f"Bias: {op.bias} ({op.confidence:.0%}), "
                f"Alignment: {op.alignment}"
            )
            if op.trade_ideas:
                for idea in op.trade_ideas[:1]:
                    parts.append(
                        f"  Trade: {idea.get('direction', '?')} "
                        f"entry={idea.get('entry_zone', '?')}, "
                        f"TP={idea.get('targets', '?')}, "
                        f"SL={idea.get('stop_loss', '?')}"
                    )
            if op.changes_from_last:
                parts.append(f"  Change: {op.changes_from_last}")

        return "\n".join(parts)

    async def _call_ai(
        self, symbol: str, current_price: float, payload: str, prev_context: str
    ) -> AnalystOpinion:
        """Send the structured data to Claude and parse the opinion."""
        system_prompt = self._prompt
        user_message = f"{payload}\n\n{prev_context}\n\nAnalyze this market data and respond with the JSON opinion."

        text, usage = await self.ai._call(
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            model=self.config.model,
            max_tokens=4096,
        )

        # Parse JSON from response
        parsed = self._parse_opinion_json(text)

        opinion = AnalystOpinion(
            timestamp=datetime.now(),
            symbol=symbol,
            current_price=current_price,
            raw_response=parsed,
            bias=parsed.get("bias", "neutral"),
            confidence=parsed.get("confidence", 0.0),
            alignment=parsed.get("alignment", ""),
            trade_ideas=parsed.get("trade_ideas", []),
            changes_from_last=parsed.get("changes_from_last", ""),
            ai_model=self.config.model,
            usage=usage,
        )
        return opinion

    def _parse_opinion_json(self, text: str) -> dict:
        """Extract and parse JSON from AI response."""
        text = text.strip()

        # Remove markdown code fences
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        # Find JSON object
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1:
            text = text[first:last + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Analyst: failed to parse AI response as JSON: {e}")
            return {
                "bias": "neutral",
                "confidence": 0.0,
                "error": "Failed to parse AI response",
                "raw_text": text[:500],
            }

    def _load_prompt(self) -> str:
        """Load the analyst system prompt."""
        from pathlib import Path
        prompt_path = Path(__file__).parent / "prompts" / "market_analyst.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        return "You are a multi-timeframe market analyst. Analyze the data and return a JSON trading opinion."
