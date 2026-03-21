"""Analyst Pattern Memory — extracts and retrieves trading lessons from scored opinions.

After each opinion is scored, this module:
1. Analyzes what went right/wrong and WHY
2. Extracts reusable lessons as skill nodes
3. Tracks per-symbol and per-level-type patterns
4. Accumulates reviewer insights (challenges that proved correct)
5. Builds a context string for the analyst prompt with relevant patterns

Uses the existing skill_nodes table with new categories:
- analyst_lesson: what went wrong/right and why
- level_pattern: how specific level types behave per symbol
- symbol_pattern: per-symbol behavioral tendencies
- review_insight: reviewer challenges that proved correct
"""

import json
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from agent.models.knowledge import SkillNode, SkillCategory, Confidence


class AnalystPatternMemory:
    """Extracts and retrieves patterns from analyst opinion outcomes."""

    def __init__(self, db):
        self.db = db

    # ── Extract Patterns from Scored Opinions ────────────────────────

    async def extract_patterns(self, opinion_id: int) -> int:
        """Extract lessons from a scored opinion. Returns number of patterns created."""
        row = await self.db._db.execute_fetchall(
            """SELECT ao.*, GROUP_CONCAT(lo.level_type || ':' || lo.price_reached || ':' || lo.price_reacted || ':' || lo.price_broke, '|') as level_results
               FROM analyst_opinions ao
               LEFT JOIN analyst_level_outcomes lo ON lo.opinion_id = ao.id
               WHERE ao.id = ? AND ao.outcome_scored = 1
               GROUP BY ao.id""",
            (opinion_id,),
        )
        if not row:
            return 0

        opinion = row[0]
        patterns_created = 0

        # 1. Extract bias lesson (what went right/wrong)
        n = await self._extract_bias_lesson(opinion)
        patterns_created += n

        # 2. Extract level patterns (which level types are reliable)
        n = await self._extract_level_patterns(opinion_id, opinion)
        patterns_created += n

        # 3. Extract symbol pattern (aggregate behavior)
        n = await self._extract_symbol_pattern(opinion)
        patterns_created += n

        # 4. Extract reviewer insights (if review data exists)
        n = await self._extract_review_insights(opinion)
        patterns_created += n

        if patterns_created > 0:
            logger.info(f"Pattern memory: extracted {patterns_created} patterns from opinion #{opinion_id}")

        return patterns_created

    async def _extract_bias_lesson(self, opinion) -> int:
        """Extract a lesson from bias correctness."""
        symbol = opinion["symbol"]
        bias = opinion["bias"]
        bias_correct = opinion["bias_correct"]
        confidence = opinion["confidence"]
        score = opinion["overall_score"] or 0

        if bias == "neutral" or bias_correct is None:
            return 0

        # Only create lessons for notable outcomes:
        # - High confidence wrong calls (important to learn from)
        # - Correct calls with good score (reinforce what works)
        if bias_correct == 0 and confidence >= 0.6:
            # Wrong call with decent confidence — important lesson
            title = f"{symbol}: {bias} call was wrong (conf {confidence:.0%})"

            # Build description from available data
            parts = [f"Called {bias} on {symbol} with {confidence:.0%} confidence but was wrong."]
            if opinion["sl_hit"]:
                parts.append("Stop loss was hit.")
            if opinion["max_adverse"] and opinion["max_adverse"] > 0:
                parts.append(f"Max adverse excursion: {opinion['max_adverse']:.1f} pips.")

            # Check what the review said (if stored in trade_ideas_json as review data)
            trade_ideas = json.loads(opinion["trade_ideas_json"] or "[]")
            if trade_ideas:
                entry = trade_ideas[0] if trade_ideas else {}
                if entry.get("stop_loss") and opinion["sl_hit"]:
                    parts.append(f"SL at {entry['stop_loss']} was too tight.")

            node = SkillNode(
                category=SkillCategory.ANALYST_LESSON,
                title=title,
                description=" ".join(parts),
                confidence=Confidence.HIGH if confidence >= 0.7 else Confidence.MEDIUM,
                source_type="analyst",
                source_id=opinion["id"],
                symbol=symbol,
                sample_size=1,
                win_rate=0.0,
                tags=[bias, "wrong_call", f"score_{int(score)}"],
            )
            await self.db.create_skill_node(node)
            return 1

        elif bias_correct == 1 and score >= 70:
            # Strong correct call — reinforce the pattern
            title = f"{symbol}: {bias} call was correct (score {score:.0f})"
            parts = [f"Called {bias} on {symbol} with {confidence:.0%} confidence — correct."]
            if opinion["tp1_hit"]:
                parts.append("TP1 was hit.")
            if opinion["tp2_hit"]:
                parts.append("TP2 was also hit.")
            parts.append(f"Max favorable: {opinion['max_favorable']:.1f}.")

            node = SkillNode(
                category=SkillCategory.ANALYST_LESSON,
                title=title,
                description=" ".join(parts),
                confidence=Confidence.HIGH,
                source_type="analyst",
                source_id=opinion["id"],
                symbol=symbol,
                sample_size=1,
                win_rate=100.0,
                tags=[bias, "correct_call", f"score_{int(score)}"],
            )
            await self.db.create_skill_node(node)
            return 1

        return 0

    async def _extract_level_patterns(self, opinion_id: int, opinion) -> int:
        """Extract patterns about how specific level types behave."""
        symbol = opinion["symbol"]

        level_rows = await self.db._db.execute_fetchall(
            """SELECT level_type, level_timeframe, level_confluence,
                      price_reached, price_reacted, price_broke, bars_to_reach
               FROM analyst_level_outcomes
               WHERE opinion_id = ?""",
            (opinion_id,),
        )

        if not level_rows:
            return 0

        # Aggregate by level_type for this symbol
        type_stats: dict[str, dict] = {}
        for row in level_rows:
            lt = row["level_type"]
            if lt not in type_stats:
                type_stats[lt] = {"total": 0, "reached": 0, "reacted": 0, "broke": 0}
            type_stats[lt]["total"] += 1
            if row["price_reached"]:
                type_stats[lt]["reached"] += 1
            if row["price_reacted"]:
                type_stats[lt]["reacted"] += 1
            if row["price_broke"]:
                type_stats[lt]["broke"] += 1

        created = 0
        for level_type, stats in type_stats.items():
            if stats["total"] < 1:
                continue

            # Check if we already have a pattern for this symbol+level_type
            existing = await self.db._db.execute_fetchall(
                """SELECT id, sample_size, win_rate, description FROM skill_nodes
                   WHERE category = 'level_pattern' AND symbol = ? AND source_type = 'analyst'
                   AND title LIKE ?""",
                (symbol, f"%{level_type}%"),
            )

            reach_rate = stats["reached"] / stats["total"] * 100
            react_rate = stats["reacted"] / max(stats["reached"], 1) * 100

            if existing:
                # Update existing pattern with new data
                ex = existing[0]
                old_n = ex["sample_size"]
                new_n = old_n + stats["total"]
                old_wr = ex["win_rate"]
                # Weighted average of old and new reach rate
                new_wr = (old_wr * old_n + reach_rate * stats["total"]) / new_n

                conf = "HIGH" if new_n >= 10 and new_wr >= 60 else "MEDIUM" if new_n >= 5 else "LOW"

                await self.db._db.execute(
                    """UPDATE skill_nodes SET sample_size = ?, win_rate = ?, confidence = ?,
                       description = ?, updated_at = ? WHERE id = ?""",
                    (new_n, round(new_wr, 1), conf,
                     f"{level_type} levels on {symbol}: reach rate {new_wr:.0f}% (n={new_n}), "
                     f"react rate {react_rate:.0f}% when reached. "
                     f"Broke through {stats['broke']}/{stats['reached']} times this batch.",
                     datetime.now().isoformat(), ex["id"]),
                )
                await self.db._db.commit()
            else:
                # Create new pattern
                node = SkillNode(
                    category=SkillCategory.LEVEL_PATTERN,
                    title=f"{symbol}: {level_type} level behavior",
                    description=(
                        f"{level_type} levels on {symbol}: reach rate {reach_rate:.0f}% "
                        f"(n={stats['total']}), react rate {react_rate:.0f}% when reached. "
                        f"Broke through {stats['broke']}/{stats['reached']} times."
                    ),
                    confidence=Confidence.LOW,
                    source_type="analyst",
                    source_id=opinion["id"],
                    symbol=symbol,
                    sample_size=stats["total"],
                    win_rate=reach_rate,
                    tags=[level_type, "level_behavior"],
                )
                await self.db.create_skill_node(node)
                created += 1

        return created

    async def _extract_symbol_pattern(self, opinion) -> int:
        """Extract/update aggregate symbol behavior pattern."""
        symbol = opinion["symbol"]

        # Get recent scored opinions for this symbol
        rows = await self.db._db.execute_fetchall(
            """SELECT bias, bias_correct, confidence, overall_score, tp1_hit, sl_hit
               FROM analyst_opinions
               WHERE symbol = ? AND outcome_scored = 1
               ORDER BY timestamp DESC LIMIT 50""",
            (symbol,),
        )

        if len(rows) < 5:
            return 0  # not enough data

        total = len(rows)
        bull_correct = sum(1 for r in rows if r["bias"] == "bullish" and r["bias_correct"] == 1)
        bull_total = sum(1 for r in rows if r["bias"] == "bullish")
        bear_correct = sum(1 for r in rows if r["bias"] == "bearish" and r["bias_correct"] == 1)
        bear_total = sum(1 for r in rows if r["bias"] == "bearish")
        avg_score = sum(r["overall_score"] or 0 for r in rows) / total
        tp1_rate = sum(1 for r in rows if r["tp1_hit"]) / total * 100
        sl_rate = sum(1 for r in rows if r["sl_hit"]) / total * 100

        bull_wr = (bull_correct / bull_total * 100) if bull_total > 0 else 0
        bear_wr = (bear_correct / bear_total * 100) if bear_total > 0 else 0

        description_parts = [
            f"{symbol} analysis performance (last {total} opinions):",
            f"Bullish accuracy: {bull_wr:.0f}% ({bull_correct}/{bull_total})",
            f"Bearish accuracy: {bear_wr:.0f}% ({bear_correct}/{bear_total})",
            f"TP1 hit rate: {tp1_rate:.0f}%, SL hit rate: {sl_rate:.0f}%",
            f"Avg score: {avg_score:.0f}/100",
        ]

        # Add specific warnings
        if bull_wr < 50 and bull_total >= 5:
            description_parts.append(f"WARNING: Bullish calls are unreliable ({bull_wr:.0f}%). Consider higher bar for bullish confidence.")
        if bear_wr < 50 and bear_total >= 5:
            description_parts.append(f"WARNING: Bearish calls are unreliable ({bear_wr:.0f}%). Consider higher bar for bearish confidence.")
        if sl_rate > 40:
            description_parts.append(f"WARNING: SL hit rate is {sl_rate:.0f}% — stops may be too tight or entries too aggressive.")

        best_bias = "bullish" if bull_wr > bear_wr else "bearish"
        description_parts.append(f"Best performing bias: {best_bias}")

        # Upsert symbol pattern
        existing = await self.db._db.execute_fetchall(
            """SELECT id FROM skill_nodes
               WHERE category = 'symbol_pattern' AND symbol = ? AND source_type = 'analyst'""",
            (symbol,),
        )

        conf = Confidence.HIGH if total >= 20 else Confidence.MEDIUM if total >= 10 else Confidence.LOW

        if existing:
            await self.db._db.execute(
                """UPDATE skill_nodes SET
                   title = ?, description = ?, confidence = ?, sample_size = ?,
                   win_rate = ?, tags = ?, updated_at = ?
                   WHERE id = ?""",
                (f"{symbol}: analyst performance profile",
                 " ".join(description_parts),
                 conf.value, total,
                 round(max(bull_wr, bear_wr), 1),
                 json.dumps([best_bias, f"n={total}", f"score_{int(avg_score)}"]),
                 datetime.now().isoformat(),
                 existing[0]["id"]),
            )
            await self.db._db.commit()
            return 0  # updated, not created
        else:
            node = SkillNode(
                category=SkillCategory.SYMBOL_PATTERN,
                title=f"{symbol}: analyst performance profile",
                description=" ".join(description_parts),
                confidence=conf,
                source_type="analyst",
                symbol=symbol,
                sample_size=total,
                win_rate=round(max(bull_wr, bear_wr), 1),
                tags=[best_bias, f"n={total}", f"score_{int(avg_score)}"],
            )
            await self.db.create_skill_node(node)
            return 1

    async def _extract_review_insights(self, opinion) -> int:
        """Extract insights from the reviewer that proved correct."""
        # The review data is stored in trade_ideas_json (which contains the revised ideas)
        # We need to check: did the reviewer's challenges predict the outcome?
        bias_correct = opinion["bias_correct"]
        confidence = opinion["confidence"]
        symbol = opinion["symbol"]

        # Load the original opinion's key_levels for context
        key_levels_above = json.loads(opinion.get("key_levels_above_json", "[]") or "[]")
        key_levels_below = json.loads(opinion.get("key_levels_below_json", "[]") or "[]")

        # If bias was wrong and we have level data, extract which levels failed
        if bias_correct == 0 and (key_levels_above or key_levels_below):
            # Check which predicted levels were NOT reached
            level_outcomes = await self.db._db.execute_fetchall(
                """SELECT level_type, level_price, direction, price_reached, price_reacted
                   FROM analyst_level_outcomes WHERE opinion_id = ?""",
                (opinion["id"],),
            )

            unreached_targets = [
                lo for lo in level_outcomes
                if not lo["price_reached"] and lo["direction"] == ("above" if opinion["bias"] == "bullish" else "below")
            ]

            if unreached_targets:
                target_types = [lo["level_type"] for lo in unreached_targets]
                title = f"{symbol}: targets unreached in wrong {opinion['bias']} call"
                desc = (
                    f"Predicted {opinion['bias']} but was wrong. "
                    f"These target levels were never reached: {', '.join(set(target_types))}. "
                    f"Consider that {', '.join(set(target_types))} levels may not be reliable "
                    f"targets for {symbol} in similar conditions."
                )

                node = SkillNode(
                    category=SkillCategory.REVIEW_INSIGHT,
                    title=title,
                    description=desc,
                    confidence=Confidence.MEDIUM,
                    source_type="analyst",
                    source_id=opinion["id"],
                    symbol=symbol,
                    sample_size=1,
                    win_rate=0.0,
                    tags=list(set(target_types)) + ["wrong_targets", opinion["bias"]],
                )
                await self.db.create_skill_node(node)
                return 1

        return 0

    # ── Build Pattern Context for Analyst Prompt ─────────────────────

    async def build_pattern_context(self, symbol: str) -> str:
        """Build a context string with relevant patterns for a specific symbol.

        Returns patterns sorted by relevance: symbol-specific first, then general.
        """
        parts = []

        # 1. Symbol performance profile
        profiles = await self.db._db.execute_fetchall(
            """SELECT title, description, confidence, sample_size FROM skill_nodes
               WHERE category = 'symbol_pattern' AND symbol = ? AND source_type = 'analyst'
               ORDER BY updated_at DESC LIMIT 1""",
            (symbol,),
        )
        if profiles:
            p = profiles[0]
            parts.append(f"### {symbol} Performance Profile ({p['confidence']}, n={p['sample_size']})")
            parts.append(p["description"])
            parts.append("")

        # 2. Recent analyst lessons for this symbol (last 10)
        lessons = await self.db._db.execute_fetchall(
            """SELECT title, description, confidence, tags FROM skill_nodes
               WHERE category = 'analyst_lesson' AND symbol = ? AND source_type = 'analyst'
               ORDER BY created_at DESC LIMIT 10""",
            (symbol,),
        )
        if lessons:
            parts.append(f"### Recent Lessons for {symbol}")
            for l in lessons:
                tags = json.loads(l["tags"]) if l["tags"] else []
                outcome = "correct" if "correct_call" in tags else "wrong"
                parts.append(f"- [{l['confidence']}] {l['title']}")
                parts.append(f"  {l['description']}")
            parts.append("")

        # 3. Level behavior patterns for this symbol
        levels = await self.db._db.execute_fetchall(
            """SELECT title, description, confidence, sample_size, win_rate FROM skill_nodes
               WHERE category = 'level_pattern' AND symbol = ? AND source_type = 'analyst'
               AND sample_size >= 3
               ORDER BY sample_size DESC LIMIT 8""",
            (symbol,),
        )
        if levels:
            parts.append(f"### Level Reliability for {symbol}")
            for l in levels:
                parts.append(f"- [{l['confidence']}, n={l['sample_size']}] {l['description']}")
            parts.append("")

        # 4. Review insights for this symbol
        reviews = await self.db._db.execute_fetchall(
            """SELECT title, description, confidence FROM skill_nodes
               WHERE category = 'review_insight' AND symbol = ? AND source_type = 'analyst'
               ORDER BY created_at DESC LIMIT 5""",
            (symbol,),
        )
        if reviews:
            parts.append(f"### Reviewer Insights for {symbol}")
            for r in reviews:
                parts.append(f"- [{r['confidence']}] {r['description']}")
            parts.append("")

        # 5. Cross-symbol lessons that might apply (HIGH confidence only)
        cross = await self.db._db.execute_fetchall(
            """SELECT title, description, symbol FROM skill_nodes
               WHERE category IN ('analyst_lesson', 'review_insight')
               AND source_type = 'analyst' AND confidence = 'HIGH'
               AND symbol != ?
               ORDER BY created_at DESC LIMIT 5""",
            (symbol,),
        )
        if cross:
            parts.append("### Lessons from Other Symbols (HIGH confidence)")
            for c in cross:
                parts.append(f"- [{c['symbol']}] {c['description']}")
            parts.append("")

        if not parts:
            return ""

        header = "## Pattern Memory (learned from past analyses)\nUse these patterns to avoid repeating mistakes and reinforce what works.\n"
        return header + "\n".join(parts)

    # ── Cleanup old patterns ─────────────────────────────────────────

    async def cleanup_stale_patterns(self, max_age_days: int = 30):
        """Remove LOW confidence analyst patterns older than max_age_days."""
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        result = await self.db._db.execute(
            """DELETE FROM skill_nodes
               WHERE source_type = 'analyst' AND confidence = 'LOW'
               AND created_at < ? AND category IN ('analyst_lesson', 'review_insight')""",
            (cutoff,),
        )
        await self.db._db.commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Pattern memory: cleaned up {deleted} stale LOW-confidence patterns")
        return deleted
