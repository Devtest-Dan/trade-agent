"""Analyst Feedback Loop — tracks opinion outcomes and builds accuracy context.

Responsibilities:
1. Persist each analyst opinion to the database
2. Score past opinions against actual price outcomes
3. Track per-level accuracy (did price reach/react at predicted levels?)
4. Compute aggregate accuracy stats
5. Build feedback context string for the analyst prompt

The scoring runs asynchronously after each new opinion, checking older
opinions that have had enough time to play out.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

# Scoring windows: how far ahead to check price
SCORE_WINDOWS = {
    "5m": 5,      # bars at M5
    "15m": 15,    # bars at M5 (15 min)
    "1h": 60,     # bars at M5 (1 hour)
    "4h": 240,    # bars at M5 (4 hours)
}

# Minimum age before scoring (in minutes) — wait for 4h candle to close
MIN_SCORE_AGE_MINUTES = 240


class AnalystFeedback:
    """Tracks analyst opinion outcomes and generates feedback for the prompt."""

    def __init__(self, db):
        self.db = db

    # ── Persist Opinion ──────────────────────────────────────────────

    async def save_opinion(self, opinion) -> int:
        """Save an analyst opinion to the database. Returns opinion ID."""
        raw = opinion.raw_response or {}

        sql = """
            INSERT INTO analyst_opinions
                (timestamp, symbol, current_price, bias, confidence, alignment,
                 trade_ideas_json, key_levels_above_json, key_levels_below_json,
                 timeframe_analysis_json, changes_from_last, computation_ms,
                 ai_model, urgency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            opinion.timestamp.isoformat(),
            opinion.symbol,
            opinion.current_price,
            opinion.bias,
            opinion.confidence,
            opinion.alignment,
            json.dumps(opinion.trade_ideas),
            json.dumps(raw.get("key_levels_above", [])),
            json.dumps(raw.get("key_levels_below", [])),
            json.dumps(raw.get("timeframe_analysis", {})),
            opinion.changes_from_last,
            opinion.computation_ms,
            opinion.ai_model,
            opinion.urgency,
        )

        cursor = await self.db._db.execute(sql, params)
        await self.db._db.commit()
        opinion_id = cursor.lastrowid

        # Save individual level predictions for tracking
        await self._save_level_predictions(opinion_id, raw, opinion.current_price)

        return opinion_id

    async def _save_level_predictions(self, opinion_id: int, raw: dict, current_price: float):
        """Extract and save key level predictions for outcome tracking."""
        levels_above = raw.get("key_levels_above", [])
        levels_below = raw.get("key_levels_below", [])

        for level_data in levels_above:
            if not isinstance(level_data, dict):
                continue
            await self.db._db.execute(
                """INSERT INTO analyst_level_outcomes
                   (opinion_id, level_price, level_type, level_timeframe,
                    level_confluence, direction)
                   VALUES (?, ?, ?, ?, ?, 'above')""",
                (opinion_id,
                 level_data.get("price", 0),
                 level_data.get("type", "unknown"),
                 level_data.get("timeframe", ""),
                 level_data.get("confluence", 1)),
            )

        for level_data in levels_below:
            if not isinstance(level_data, dict):
                continue
            await self.db._db.execute(
                """INSERT INTO analyst_level_outcomes
                   (opinion_id, level_price, level_type, level_timeframe,
                    level_confluence, direction)
                   VALUES (?, ?, ?, ?, ?, 'below')""",
                (opinion_id,
                 level_data.get("price", 0),
                 level_data.get("type", "unknown"),
                 level_data.get("timeframe", ""),
                 level_data.get("confluence", 1)),
            )

        await self.db._db.commit()

    # ── Score Past Opinions ──────────────────────────────────────────

    async def score_pending_opinions(self, bridge) -> int:
        """Score all opinions old enough to have outcomes. Returns count scored."""
        cutoff = datetime.now() - timedelta(minutes=MIN_SCORE_AGE_MINUTES)

        rows = await self.db._db.execute_fetchall(
            """SELECT id, timestamp, symbol, current_price, bias, confidence,
                      trade_ideas_json, key_levels_above_json, key_levels_below_json
               FROM analyst_opinions
               WHERE outcome_scored = 0 AND timestamp < ?
               ORDER BY timestamp ASC LIMIT 20""",
            (cutoff.isoformat(),),
        )

        scored = 0
        for row in rows:
            try:
                await self._score_opinion(row, bridge)
                scored += 1
            except Exception as e:
                logger.warning(f"Failed to score opinion #{row['id']}: {e}")

        if scored > 0:
            await self._update_accuracy_stats(rows[0]["symbol"] if rows else "XAUUSD")
            logger.info(f"Analyst feedback: scored {scored} opinions")

        return scored

    async def _score_opinion(self, row, bridge):
        """Score a single opinion against actual price data."""
        opinion_id = row["id"]
        symbol = row["symbol"]
        opinion_price = row["current_price"]
        bias = row["bias"]
        trade_ideas = json.loads(row["trade_ideas_json"] or "[]")

        # Fetch bars since the opinion was created
        bars = await bridge.get_bars(symbol, "M5", 300)
        if not bars:
            return

        # Find the bar closest to opinion timestamp
        opinion_time = datetime.fromisoformat(row["timestamp"])
        opinion_bar_idx = None
        for i, bar in enumerate(bars):
            if bar.time >= opinion_time:
                opinion_bar_idx = i
                break

        if opinion_bar_idx is None:
            return  # opinion is older than available bars

        remaining = len(bars) - opinion_bar_idx

        # Get prices at scoring windows
        price_5m = bars[min(opinion_bar_idx + 1, len(bars) - 1)].close if remaining > 1 else None
        price_15m = bars[min(opinion_bar_idx + 3, len(bars) - 1)].close if remaining > 3 else None
        price_1h = bars[min(opinion_bar_idx + 12, len(bars) - 1)].close if remaining > 12 else None
        price_4h = bars[min(opinion_bar_idx + 48, len(bars) - 1)].close if remaining > 48 else None

        # Max favorable and adverse excursion
        future_bars = bars[opinion_bar_idx:]
        highs = [b.high for b in future_bars]
        lows = [b.low for b in future_bars]
        max_high = max(highs) if highs else opinion_price
        min_low = min(lows) if lows else opinion_price

        if bias == "bullish":
            max_favorable = max_high - opinion_price
            max_adverse = opinion_price - min_low
        elif bias == "bearish":
            max_favorable = opinion_price - min_low
            max_adverse = max_high - opinion_price
        else:
            max_favorable = max(max_high - opinion_price, opinion_price - min_low)
            max_adverse = 0.0

        # Bias correctness: did price move in the predicted direction?
        check_price = price_1h or price_15m or price_5m
        bias_correct = None
        if check_price is not None:
            if bias == "bullish":
                bias_correct = check_price > opinion_price
            elif bias == "bearish":
                bias_correct = check_price < opinion_price
            else:
                bias_correct = None  # neutral = no prediction

        # Check trade ideas (TP/SL)
        tp1_hit = False
        tp2_hit = False
        sl_hit = False
        for idea in trade_ideas:
            targets = idea.get("targets", [])
            stop_loss = idea.get("stop_loss")
            direction = idea.get("direction", "long")

            if targets:
                if direction == "long":
                    if len(targets) >= 1 and max_high >= targets[0]:
                        tp1_hit = True
                    if len(targets) >= 2 and max_high >= targets[1]:
                        tp2_hit = True
                else:
                    if len(targets) >= 1 and min_low <= targets[0]:
                        tp1_hit = True
                    if len(targets) >= 2 and min_low <= targets[1]:
                        tp2_hit = True

            if stop_loss is not None:
                if direction == "long" and min_low <= stop_loss:
                    sl_hit = True
                elif direction == "short" and max_high >= stop_loss:
                    sl_hit = True

        # Overall score (0-100): weighted combination
        score = 0.0
        components = 0
        if bias_correct is not None:
            score += 40.0 if bias_correct else 0.0
            components += 1
        if trade_ideas:
            if tp1_hit:
                score += 30.0
            if not sl_hit:
                score += 20.0
            if tp2_hit:
                score += 10.0
            components += 1
        if components > 0:
            # Normalize: bias worth 40, trades worth 60
            pass
        else:
            score = 50.0  # neutral, no prediction

        # Update the opinion record
        await self.db._db.execute(
            """UPDATE analyst_opinions SET
                outcome_scored = 1, outcome_scored_at = ?,
                bias_correct = ?, price_after_5m = ?, price_after_15m = ?,
                price_after_1h = ?, price_after_4h = ?,
                max_favorable = ?, max_adverse = ?,
                tp1_hit = ?, tp2_hit = ?, sl_hit = ?, overall_score = ?
               WHERE id = ?""",
            (datetime.now().isoformat(),
             1 if bias_correct else (0 if bias_correct is False else None),
             price_5m, price_15m, price_1h, price_4h,
             round(max_favorable, 2), round(max_adverse, 2),
             1 if tp1_hit else 0, 1 if tp2_hit else 0,
             1 if sl_hit else 0, round(score, 1),
             opinion_id),
        )

        # Score individual level predictions
        await self._score_levels(opinion_id, future_bars, opinion_price)

        await self.db._db.commit()

    async def _score_levels(self, opinion_id: int, future_bars, opinion_price: float):
        """Score each predicted level: did price reach it? react? break through?"""
        if not future_bars:
            return

        highs = [b.high for b in future_bars]
        lows = [b.low for b in future_bars]

        rows = await self.db._db.execute_fetchall(
            "SELECT id, level_price, direction FROM analyst_level_outcomes WHERE opinion_id = ?",
            (opinion_id,),
        )

        for row in rows:
            level = row["level_price"]
            if level <= 0:
                continue

            reached = False
            reacted = False
            broke = False
            bars_to_reach = None

            for i, bar in enumerate(future_bars):
                if row["direction"] == "above":
                    if bar.high >= level:
                        reached = True
                        if bars_to_reach is None:
                            bars_to_reach = i
                        # Reacted = touched then reversed (next bar lower)
                        if i + 1 < len(future_bars) and future_bars[i + 1].close < level:
                            reacted = True
                        # Broke = closed above
                        if bar.close > level:
                            broke = True
                        break
                else:  # below
                    if bar.low <= level:
                        reached = True
                        if bars_to_reach is None:
                            bars_to_reach = i
                        if i + 1 < len(future_bars) and future_bars[i + 1].close > level:
                            reacted = True
                        if bar.close < level:
                            broke = True
                        break

            await self.db._db.execute(
                """UPDATE analyst_level_outcomes SET
                    price_reached = ?, price_reacted = ?, price_broke = ?, bars_to_reach = ?
                   WHERE id = ?""",
                (1 if reached else 0, 1 if reacted else 0, 1 if broke else 0,
                 bars_to_reach, row["id"]),
            )

    # ── Accuracy Stats ───────────────────────────────────────────────

    async def _update_accuracy_stats(self, symbol: str):
        """Recompute aggregate accuracy stats for all time periods."""
        periods = {
            "last_24h": 1,
            "last_7d": 7,
            "last_30d": 30,
            "all_time": 9999,
        }

        for period_name, days in periods.items():
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            rows = await self.db._db.execute_fetchall(
                """SELECT bias, confidence, bias_correct, tp1_hit, tp2_hit, sl_hit,
                          max_favorable, max_adverse, overall_score
                   FROM analyst_opinions
                   WHERE symbol = ? AND outcome_scored = 1 AND timestamp > ?""",
                (symbol, cutoff),
            )

            if not rows:
                continue

            total = len(rows)
            bias_correct_count = sum(1 for r in rows if r["bias_correct"] == 1)
            avg_confidence = sum(r["confidence"] for r in rows) / total
            tp1_hits = sum(1 for r in rows if r["tp1_hit"])
            tp2_hits = sum(1 for r in rows if r["tp2_hit"])
            sl_hits = sum(1 for r in rows if r["sl_hit"])
            avg_favorable = sum(r["max_favorable"] or 0 for r in rows) / total
            avg_adverse = sum(r["max_adverse"] or 0 for r in rows) / total
            scored_with_bias = sum(1 for r in rows if r["bias_correct"] is not None)
            avg_score = sum(r["overall_score"] or 0 for r in rows) / total

            # Level stats
            level_rows = await self.db._db.execute_fetchall(
                """SELECT price_reached, price_reacted FROM analyst_level_outcomes lo
                   JOIN analyst_opinions ao ON lo.opinion_id = ao.id
                   WHERE ao.symbol = ? AND ao.timestamp > ?""",
                (symbol, cutoff),
            )
            level_reach = sum(1 for r in level_rows if r["price_reached"]) / max(len(level_rows), 1)
            level_react = sum(1 for r in level_rows if r["price_reacted"]) / max(len(level_rows), 1)

            # Find worst bias
            bias_counts = {}
            for r in rows:
                b = r["bias"]
                if b not in bias_counts:
                    bias_counts[b] = {"correct": 0, "total": 0}
                bias_counts[b]["total"] += 1
                if r["bias_correct"] == 1:
                    bias_counts[b]["correct"] += 1
            worst_bias = min(bias_counts, key=lambda b: bias_counts[b]["correct"] / max(bias_counts[b]["total"], 1)) if bias_counts else ""

            await self.db._db.execute(
                """INSERT OR REPLACE INTO analyst_accuracy_stats
                   (symbol, stat_period, total_opinions, bias_accuracy, avg_confidence,
                    tp1_hit_rate, tp2_hit_rate, sl_hit_rate,
                    avg_max_favorable, avg_max_adverse,
                    level_reach_rate, level_react_rate,
                    worst_bias, avg_score, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, period_name, total,
                 round(bias_correct_count / max(scored_with_bias, 1) * 100, 1),
                 round(avg_confidence * 100, 1),
                 round(tp1_hits / total * 100, 1),
                 round(tp2_hits / total * 100, 1),
                 round(sl_hits / total * 100, 1),
                 round(avg_favorable, 2),
                 round(avg_adverse, 2),
                 round(level_reach * 100, 1),
                 round(level_react * 100, 1),
                 worst_bias,
                 round(avg_score, 1),
                 datetime.now().isoformat()),
            )

        await self.db._db.commit()

    # ── Feedback for Analyst Prompt ──────────────────────────────────

    async def build_feedback_context(self, symbol: str) -> str:
        """Build a feedback string for the analyst's system prompt.

        This tells the AI how accurate its recent predictions have been,
        so it can calibrate confidence and adjust strategy.
        """
        parts = []

        # Get accuracy stats
        rows = await self.db._db.execute_fetchall(
            "SELECT * FROM analyst_accuracy_stats WHERE symbol = ? ORDER BY stat_period",
            (symbol,),
        )

        if not rows:
            return ""

        parts.append("## Your Recent Accuracy (self-assessment feedback)")
        parts.append("Use this to calibrate your confidence levels and adjust your analysis.\n")

        for row in rows:
            period = row["stat_period"].replace("_", " ")
            parts.append(f"### {period} ({row['total_opinions']} opinions)")
            parts.append(f"- Bias accuracy: {row['bias_accuracy']}%")
            parts.append(f"- TP1 hit rate: {row['tp1_hit_rate']}%")
            parts.append(f"- TP2 hit rate: {row['tp2_hit_rate']}%")
            parts.append(f"- SL hit rate: {row['sl_hit_rate']}%")
            parts.append(f"- Avg max favorable: {row['avg_max_favorable']}")
            parts.append(f"- Avg max adverse: {row['avg_max_adverse']}")
            parts.append(f"- Level reach rate: {row['level_reach_rate']}%")
            parts.append(f"- Level reaction rate: {row['level_react_rate']}%")
            if row["worst_bias"]:
                parts.append(f"- Least accurate bias: {row['worst_bias']}")
            parts.append(f"- Avg score: {row['avg_score']}/100")
            parts.append("")

        # Get recent scored opinions for specific lessons
        recent = await self.db._db.execute_fetchall(
            """SELECT bias, confidence, bias_correct, tp1_hit, sl_hit, overall_score,
                      current_price, price_after_1h, max_favorable, max_adverse
               FROM analyst_opinions
               WHERE symbol = ? AND outcome_scored = 1
               ORDER BY timestamp DESC LIMIT 10""",
            (symbol,),
        )

        if recent:
            parts.append("### Last 10 Scored Opinions")
            for r in recent:
                correct = "correct" if r["bias_correct"] == 1 else "wrong" if r["bias_correct"] == 0 else "neutral"
                tp = "TP1 hit" if r["tp1_hit"] else "TP1 missed"
                sl = "SL hit" if r["sl_hit"] else "SL safe"
                parts.append(
                    f"- {r['bias']} ({r['confidence']:.0%} conf) -> {correct}, "
                    f"{tp}, {sl}, score={r['overall_score']}"
                )

            # Specific warnings
            wrong_high_conf = [r for r in recent if r["bias_correct"] == 0 and r["confidence"] >= 0.7]
            if wrong_high_conf:
                parts.append(f"\nWARNING: {len(wrong_high_conf)} high-confidence calls were wrong recently. Consider lowering confidence thresholds.")

            sl_hit_count = sum(1 for r in recent if r["sl_hit"])
            if sl_hit_count >= 5:
                parts.append(f"\nWARNING: SL was hit in {sl_hit_count}/10 recent opinions. Consider wider stops or more conservative entries.")

        return "\n".join(parts)

    # ── API helpers ──────────────────────────────────────────────────

    async def get_accuracy_stats(self, symbol: str) -> list[dict]:
        """Get accuracy stats for the API."""
        rows = await self.db._db.execute_fetchall(
            "SELECT * FROM analyst_accuracy_stats WHERE symbol = ? ORDER BY stat_period",
            (symbol,),
        )
        return [dict(r) for r in rows]

    async def get_scored_opinions(self, symbol: str, limit: int = 20) -> list[dict]:
        """Get recent scored opinions for the API."""
        rows = await self.db._db.execute_fetchall(
            """SELECT id, timestamp, symbol, current_price, bias, confidence,
                      bias_correct, tp1_hit, tp2_hit, sl_hit, overall_score,
                      price_after_5m, price_after_15m, price_after_1h, price_after_4h,
                      max_favorable, max_adverse, urgency
               FROM analyst_opinions
               WHERE symbol = ? AND outcome_scored = 1
               ORDER BY timestamp DESC LIMIT ?""",
            (symbol, limit),
        )
        return [dict(r) for r in rows]
