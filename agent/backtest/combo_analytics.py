"""Condition-combination analytics — find which rule combos predict wins vs losses."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from itertools import combinations

from agent.backtest.models import BacktestTrade


@dataclass
class ComboStat:
    """Statistics for a specific rule combination."""
    rules: list[str]  # rule descriptions
    total: int = 0
    wins: int = 0
    losses: int = 0
    avg_pnl: float = 0.0
    win_rate: float = 0.0
    avg_rr: float = 0.0


@dataclass
class ComboAnalyticsResult:
    """Full combination analytics results."""
    total_trades: int = 0
    # Full combos (all rules that fired together)
    full_combos: list[ComboStat] = field(default_factory=list)
    # Pair combos (every 2-rule subset)
    pair_combos: list[ComboStat] = field(default_factory=list)
    # Single rule stats
    single_rules: list[ComboStat] = field(default_factory=list)
    # Best/worst combos
    best_combo: ComboStat | None = None
    worst_combo: ComboStat | None = None


def analyze_combinations(
    trades: list[BacktestTrade],
    min_occurrences: int = 3,
) -> ComboAnalyticsResult:
    """Analyze which rule combinations correlate with wins vs losses.

    Args:
        trades: List of backtest trades with fired_rules populated
        min_occurrences: Minimum number of trades for a combo to be reported
    """
    result = ComboAnalyticsResult(total_trades=len(trades))

    # Only analyze trades with fired_rules
    trades_with_rules = [t for t in trades if t.fired_rules]
    if len(trades_with_rules) < min_occurrences:
        return result

    # --- Full combos (sorted tuple of all passed rule descriptions) ---
    full_stats: dict[tuple[str, ...], list[BacktestTrade]] = {}
    # --- Pair combos ---
    pair_stats: dict[tuple[str, str], list[BacktestTrade]] = {}
    # --- Single rules ---
    single_stats: dict[str, list[BacktestTrade]] = {}

    for trade in trades_with_rules:
        # Get descriptions of rules that passed
        passed_rules = sorted(set(
            r.get("description") or r.get("left_expr", "?")
            for r in trade.fired_rules
            if r.get("passed", True)
        ))
        if not passed_rules:
            continue

        # Full combo key
        combo_key = tuple(passed_rules)
        full_stats.setdefault(combo_key, []).append(trade)

        # Pairs
        if len(passed_rules) >= 2:
            for pair in combinations(passed_rules, 2):
                pair_stats.setdefault(pair, []).append(trade)

        # Singles
        for rule in passed_rules:
            single_stats.setdefault(rule, []).append(trade)

    # Convert to ComboStat objects
    result.full_combos = _build_stats(full_stats, min_occurrences)
    result.pair_combos = _build_stats(pair_stats, min_occurrences)
    result.single_rules = _build_stats(single_stats, min_occurrences)

    # Find best/worst full combo by win rate (among those with enough samples)
    if result.full_combos:
        result.best_combo = max(result.full_combos, key=lambda c: c.win_rate)
        result.worst_combo = min(result.full_combos, key=lambda c: c.win_rate)

    return result


def _build_stats(
    stats_map: dict[tuple | str, list[BacktestTrade]],
    min_occurrences: int,
) -> list[ComboStat]:
    """Convert trade groupings into sorted ComboStat list."""
    results = []
    for key, trade_list in stats_map.items():
        if len(trade_list) < min_occurrences:
            continue

        rules = list(key) if isinstance(key, tuple) else [key]
        wins = len([t for t in trade_list if t.outcome == "win"])
        losses = len([t for t in trade_list if t.outcome == "loss"])
        pnls = [t.pnl for t in trade_list]
        rrs = [t.rr_achieved for t in trade_list if t.rr_achieved is not None]

        results.append(ComboStat(
            rules=rules,
            total=len(trade_list),
            wins=wins,
            losses=losses,
            avg_pnl=round(statistics.mean(pnls), 2),
            win_rate=round(wins / len(trade_list) * 100, 1),
            avg_rr=round(statistics.mean(rrs), 2) if rrs else 0.0,
        ))

    # Sort by total descending, then win_rate descending
    results.sort(key=lambda c: (c.total, c.win_rate), reverse=True)
    return results
