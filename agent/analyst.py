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
    interval_seconds: int = 60  # base interval when coasting (no nearby levels)
    model: str = "sonnet"  # AI model to use (haiku for cost saving, sonnet for quality)
    max_history: int = 5  # keep last N opinions for context
    indicators: list[AnalystIndicator] = field(default_factory=list)

    # Adaptive scheduling — like a human trader, check more often near key levels
    adaptive_enabled: bool = True
    interval_alert: int = 15     # seconds when price is very close to key level (< 0.5× ATR)
    interval_approach: int = 30  # seconds when price is approaching key level (< 1.5× ATR)
    interval_nearby: int = 45    # seconds when price is near a level (< 3× ATR)
    interval_coast: int = 60     # seconds when nothing interesting is nearby (default)
    interval_quiet: int = 120    # seconds during low-volatility / no levels in range

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
    # Adaptive scheduling info
    nearest_level_distance: float = 0.0  # distance to nearest key level in price
    nearest_level_atr_multiple: float = 0.0  # distance as multiple of ATR
    next_interval: int = 60  # seconds until next check
    urgency: str = "coast"  # alert / approach / nearby / coast / quiet


# ── Core Analyst ─────────────────────────────────────────────────────

class ContinuousAnalyst:
    """Runs a background loop that continuously analyzes the market."""

    def __init__(self, bridge: ZMQBridge, ai_service: AIService, config: AnalystConfig | None = None, feedback=None):
        self.bridge = bridge
        self.ai = ai_service
        self.config = config or AnalystConfig()
        self.feedback = feedback  # AnalystFeedback instance (optional)
        self._task: asyncio.Task | None = None
        self._running = False
        self._opinions: list[AnalystOpinion] = []
        self._callbacks: list = []
        self._prompt = self._load_prompt()
        self._last_indicator_data: dict[str, dict] = {}  # cached for proximity checks
        self._feedback_context: str = ""  # cached feedback for prompt
        self._score_counter: int = 0  # score every N cycles

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
        """Background loop with adaptive frequency — checks faster near key levels."""
        logger.info("Analyst loop started")
        next_sleep = self.config.interval_coast

        # Load feedback context on start
        await self._refresh_feedback_context()

        while self._running:
            try:
                opinion = await self._run_analysis()
                if opinion:
                    # Compute adaptive interval based on proximity to key levels
                    next_sleep = self._compute_next_interval(opinion)
                    opinion.next_interval = next_sleep

                    # Persist opinion and score old ones
                    await self._feedback_cycle(opinion)

                    for cb in self._callbacks:
                        try:
                            result = cb(opinion)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.error(f"Analyst callback error: {e}")
                else:
                    # No data — use base interval
                    next_sleep = self.config.interval_coast
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Analyst loop error: {e}")
                next_sleep = self.config.interval_coast

            # Wait for the dynamically computed interval
            try:
                logger.debug(f"Analyst sleeping {next_sleep}s (urgency: {self._opinions[-1].urgency if self._opinions else '?'})")
                await asyncio.sleep(next_sleep)
            except asyncio.CancelledError:
                break

        logger.info("Analyst loop stopped")

    async def _feedback_cycle(self, opinion: AnalystOpinion):
        """Save opinion to DB and periodically score old ones + refresh feedback."""
        if not self.feedback:
            return
        try:
            await self.feedback.save_opinion(opinion)
            self._score_counter += 1
            # Score pending opinions every 10 cycles (~10 min at 60s interval)
            if self._score_counter >= 10:
                self._score_counter = 0
                scored = await self.feedback.score_pending_opinions(self.bridge)
                if scored > 0:
                    await self._refresh_feedback_context()
        except Exception as e:
            logger.warning(f"Feedback cycle error: {e}")

    async def _refresh_feedback_context(self):
        """Refresh the cached feedback context for the AI prompt."""
        if not self.feedback:
            return
        try:
            self._feedback_context = await self.feedback.build_feedback_context(self.config.symbol)
            if self._feedback_context:
                logger.info("Analyst feedback context refreshed")
        except Exception as e:
            logger.warning(f"Failed to refresh feedback context: {e}")

    def _compute_next_interval(self, opinion: AnalystOpinion) -> int:
        """Determine next check interval based on price proximity to key levels.

        Like a human trader:
        - Far from all levels → relax, check every 60-120s
        - Approaching a level → lean in, check every 30-45s
        - Right at a level → full attention, check every 15s
        """
        if not self.config.adaptive_enabled:
            return self.config.interval_seconds

        price = opinion.current_price
        if price <= 0:
            return self.config.interval_coast

        # Get ATR from any timeframe (prefer H1, fallback to whatever is available)
        atr = self._get_atr_from_opinion(opinion)
        if atr <= 0:
            return self.config.interval_coast

        # Collect all key levels from the AI opinion
        levels = self._extract_key_levels(opinion)

        if not levels:
            opinion.urgency = "quiet"
            opinion.nearest_level_distance = 0
            opinion.nearest_level_atr_multiple = 0
            return self.config.interval_quiet

        # Find nearest level
        min_distance = float("inf")
        for level in levels:
            distance = abs(price - level)
            if distance < min_distance:
                min_distance = distance

        atr_multiple = min_distance / atr if atr > 0 else 999

        opinion.nearest_level_distance = round(min_distance, 2)
        opinion.nearest_level_atr_multiple = round(atr_multiple, 2)

        # Determine urgency tier
        if atr_multiple < 0.5:
            opinion.urgency = "alert"
            interval = self.config.interval_alert
        elif atr_multiple < 1.5:
            opinion.urgency = "approach"
            interval = self.config.interval_approach
        elif atr_multiple < 3.0:
            opinion.urgency = "nearby"
            interval = self.config.interval_nearby
        else:
            opinion.urgency = "coast"
            interval = self.config.interval_coast

        # Also speed up if confidence is high and trade ideas exist
        if opinion.confidence >= 0.75 and opinion.trade_ideas:
            interval = min(interval, self.config.interval_approach)
            if opinion.urgency == "coast":
                opinion.urgency = "nearby"

        logger.info(
            f"Adaptive: nearest level {min_distance:.1f} away "
            f"({atr_multiple:.1f}× ATR) → urgency={opinion.urgency}, "
            f"next check in {interval}s"
        )
        return interval

    def _get_atr_from_opinion(self, opinion: AnalystOpinion) -> float:
        """Extract ATR value from the opinion's raw indicator data.

        Falls back through timeframes: H1 → H4 → M15 → first available.
        """
        raw = opinion.raw_response
        tf_analysis = raw.get("timeframe_analysis", {})

        # ATR isn't in the AI output directly — get it from the last computed indicators
        # We stored indicator data during _run_analysis, check the cached engines
        # Instead, use a simple proxy: recent candle range as rough ATR estimate
        # Better: look at the actual indicator computation results we passed to AI

        # The indicator data is embedded in the payload text, not in the JSON response.
        # So we need to cache it. Let's check if we saved it.
        if hasattr(self, "_last_indicator_data") and self._last_indicator_data:
            # Try H1 ATR first, then H4, then any
            for tf_prefix in ["h1_atr", "h4_atr", "m15_atr", "d1_atr"]:
                ind = self._last_indicator_data.get(tf_prefix)
                if ind and ind.get("values", {}).get("value", 0) > 0:
                    return ind["values"]["value"]

        # Fallback: estimate from price (0.1% of price as rough ATR)
        return opinion.current_price * 0.001

    def _extract_key_levels(self, opinion: AnalystOpinion) -> list[float]:
        """Extract all key price levels from the AI opinion for proximity check."""
        levels = []
        raw = opinion.raw_response

        # From AI's key_levels_above and key_levels_below
        for level_data in raw.get("key_levels_above", []):
            if isinstance(level_data, dict):
                if "price" in level_data:
                    levels.append(float(level_data["price"]))
                if "zone" in level_data and isinstance(level_data["zone"], list):
                    for z in level_data["zone"]:
                        levels.append(float(z))
            elif isinstance(level_data, (int, float)):
                levels.append(float(level_data))

        for level_data in raw.get("key_levels_below", []):
            if isinstance(level_data, dict):
                if "price" in level_data:
                    levels.append(float(level_data["price"]))
                if "zone" in level_data and isinstance(level_data["zone"], list):
                    for z in level_data["zone"]:
                        levels.append(float(z))
            elif isinstance(level_data, (int, float)):
                levels.append(float(level_data))

        # From trade ideas (entry zones, SL, TP)
        for idea in raw.get("trade_ideas", []):
            if isinstance(idea, dict):
                if "stop_loss" in idea:
                    levels.append(float(idea["stop_loss"]))
                for target in idea.get("targets", []):
                    levels.append(float(target))
                zone = idea.get("entry_zone", [])
                if isinstance(zone, list):
                    for z in zone:
                        levels.append(float(z))

        # Also pull from cached indicator data (SMC strong levels, OB zones, NWE bands)
        if hasattr(self, "_last_indicator_data") and self._last_indicator_data:
            for ind_id, ind in self._last_indicator_data.items():
                vals = ind.get("values", {})
                name = ind.get("name", "")

                if name == "SMC_Structure":
                    for k in ["strong_high", "strong_low", "equilibrium", "ote_top", "ote_bottom"]:
                        v = vals.get(k, 0)
                        if v and v > 0:
                            levels.append(v)

                elif name == "OB_FVG":
                    for k in ["ob_upper", "ob_lower", "fvg_upper", "fvg_lower"]:
                        v = vals.get(k, 0)
                        if v and v > 0:
                            levels.append(v)

                elif name == "NW_Envelope":
                    for k in ["upper_far", "upper_near", "lower_near", "lower_far", "yhat"]:
                        v = vals.get(k, 0)
                        if v and v > 0:
                            levels.append(v)

                elif name == "TPO":
                    for k in ["poc", "vah", "val"]:
                        v = vals.get(k, 0)
                        if v and v > 0:
                            levels.append(v)

                elif name == "Bollinger":
                    for k in ["upper", "lower"]:
                        v = vals.get(k, 0)
                        if v and v > 0:
                            levels.append(v)

                elif name == "EMA":
                    v = vals.get("value", 0)
                    if v and v > 0:
                        levels.append(v)

        # Deduplicate and filter out zeros
        return list(set(l for l in levels if l > 0))

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
        self._last_indicator_data = indicator_data  # cache for adaptive scheduling

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
        if self._feedback_context:
            system_prompt += f"\n\n{self._feedback_context}"
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
