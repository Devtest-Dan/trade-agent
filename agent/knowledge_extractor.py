"""Extract atomic trading insights from backtest results into skill graph nodes."""

from collections import defaultdict
from typing import Any

from loguru import logger

from agent.db.database import Database
from agent.models.knowledge import (
    SkillNode, SkillEdge, SkillCategory, Confidence, EdgeRelationship,
)


async def extract_skills_from_backtest(
    db: Database,
    run_id: int,
    playbook_id: int,
    symbol: str,
    timeframe: str,
    trades: list[dict],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Extract skill nodes from a completed backtest.

    Groups trades by (market_regime, phase_at_entry), computes stats,
    creates SkillNodes for groups and individual indicator insights,
    and connects them with SkillEdges.

    Returns: {nodes_created, edges_created, nodes: [...]}
    """
    # Clean up any previous extraction for this backtest
    deleted = await db.delete_skills_for_backtest(run_id)
    if deleted:
        logger.info(f"Deleted {deleted} previous skill nodes for backtest {run_id}")

    groups = _group_trades(trades)
    created_nodes: list[SkillNode] = []
    # Map group_key -> parent node for linking indicator nodes
    group_parent_nodes: dict[tuple[str, str], SkillNode] = {}
    edges_created = 0

    # --- Pass 1: Group-level nodes (entry_pattern, exit_signal, etc.) ---
    for group_key, group_trades in groups.items():
        if len(group_trades) < 3:
            continue

        regime, phase = group_key
        stats = _compute_group_stats(group_trades)
        indicators = _analyze_indicator_ranges(group_trades)
        category = _categorize_group(phase, stats)
        confidence = _determine_confidence(len(group_trades), stats["win_rate"])
        title = _generate_title_template(category, regime, phase, symbol, stats)
        description = _generate_description_template(
            category, regime, phase, symbol, timeframe, stats, indicators
        )

        node = SkillNode(
            category=category,
            title=title,
            description=description,
            confidence=confidence,
            source_type="backtest",
            source_id=run_id,
            playbook_id=playbook_id,
            symbol=symbol,
            timeframe=timeframe,
            market_regime=regime,
            sample_size=len(group_trades),
            win_rate=stats["win_rate"],
            avg_pnl=stats["avg_pnl"],
            avg_rr=stats["avg_rr"],
            indicators_json=indicators if indicators else None,
            tags=[regime, phase, category.value] if regime else [phase, category.value],
        )
        node_id = await db.create_skill_node(node)
        node.id = node_id
        created_nodes.append(node)
        group_parent_nodes[group_key] = node

    # --- Pass 2: Indicator insight nodes ---
    for group_key, group_trades in groups.items():
        if len(group_trades) < 3:
            continue

        regime, phase = group_key
        parent_node = group_parent_nodes.get(group_key)
        indicator_nodes = _extract_indicator_insights(
            group_trades, run_id, playbook_id, symbol, timeframe, regime, phase
        )

        for ind_node in indicator_nodes:
            node_id = await db.create_skill_node(ind_node)
            ind_node.id = node_id
            created_nodes.append(ind_node)

            # Edge: indicator insight <-> parent group node
            if parent_node:
                edge = SkillEdge(
                    source_id=parent_node.id,
                    target_id=ind_node.id,
                    relationship=EdgeRelationship.COMBINES_WITH,
                    weight=0.8,
                    reason=f"Indicator insight extracted from {phase} group",
                )
                await db.create_skill_edge(edge)
                edges_created += 1

    # --- Pass 3: Cross-node edges (within batch + existing DB nodes) ---
    for node in created_nodes:
        overlapping = await _find_overlapping_nodes(db, node, created_nodes)
        for other in overlapping:
            if other.id == node.id:
                continue
            rel, weight, reason = _compute_edge_relationship(node, other)
            edge = SkillEdge(
                source_id=node.id,
                target_id=other.id,
                relationship=rel,
                weight=weight,
                reason=reason,
            )
            await db.create_skill_edge(edge)
            edges_created += 1

    logger.info(
        f"Extracted {len(created_nodes)} skill nodes and {edges_created} edges "
        f"from backtest {run_id}"
    )

    return {
        "nodes_created": len(created_nodes),
        "edges_created": edges_created,
        "nodes": [n.model_dump(mode="json") for n in created_nodes],
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _flatten_indicators(entry_ind: dict) -> dict[str, float]:
    """Flatten nested indicator dicts into dot-notation keys.

    e.g. {"h4_smc": {"trend": 1.0, "zone": -1.0}} -> {"h4_smc.trend": 1.0, "h4_smc.zone": -1.0}
    """
    flat: dict[str, float] = {}
    for k, v in entry_ind.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if isinstance(sub_v, (int, float)) and sub_v == sub_v:
                    flat[f"{k}.{sub_k}"] = float(sub_v)
        elif isinstance(v, (int, float)) and v == v:
            flat[k] = float(v)
    return flat


def _group_trades(trades: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Group trades by (market_regime, phase_at_entry)."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in trades:
        regime = t.get("market_regime") or t.get("phase_at_entry", "unknown")
        phase = t.get("phase_at_entry", "unknown")
        groups[(regime, phase)].append(t)
    return groups


def _compute_group_stats(trades: list[dict]) -> dict[str, Any]:
    """Compute win rate, avg PnL, avg RR for a group of trades."""
    total = len(trades)
    wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    pnls = [t.get("pnl", 0) or 0 for t in trades]
    rrs = [t.get("rr_achieved", 0) or 0 for t in trades]

    return {
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "avg_pnl": round(sum(pnls) / total, 4) if total > 0 else 0,
        "total_pnl": round(sum(pnls), 4),
        "avg_rr": round(sum(rrs) / total, 2) if total > 0 else 0,
        "best_pnl": round(max(pnls), 4) if pnls else 0,
        "worst_pnl": round(min(pnls), 4) if pnls else 0,
    }


def _analyze_indicator_ranges(trades: list[dict]) -> dict[str, Any]:
    """Analyze indicator values at entry for winners vs all trades.

    Flattens nested indicator objects into dot-notation keys.
    """
    winners = [t for t in trades if (t.get("pnl") or 0) > 0]
    all_indicators: dict[str, list[float]] = defaultdict(list)
    winner_indicators: dict[str, list[float]] = defaultdict(list)

    for t in trades:
        entry_ind = t.get("entry_indicators") or t.get("variables_at_entry") or {}
        flat = _flatten_indicators(entry_ind)
        for k, v in flat.items():
            all_indicators[k].append(v)

    for t in winners:
        entry_ind = t.get("entry_indicators") or t.get("variables_at_entry") or {}
        flat = _flatten_indicators(entry_ind)
        for k, v in flat.items():
            winner_indicators[k].append(v)

    result = {}
    for ind_name, values in all_indicators.items():
        win_vals = winner_indicators.get(ind_name, [])
        entry = {
            "all_min": round(min(values), 4),
            "all_max": round(max(values), 4),
            "all_mean": round(sum(values) / len(values), 4),
        }
        if win_vals:
            entry["win_min"] = round(min(win_vals), 4)
            entry["win_max"] = round(max(win_vals), 4)
            entry["win_mean"] = round(sum(win_vals) / len(win_vals), 4)
        result[ind_name] = entry

    return result


def _extract_indicator_insights(
    trades: list[dict],
    run_id: int,
    playbook_id: int,
    symbol: str,
    timeframe: str,
    regime: str,
    phase: str,
) -> list[SkillNode]:
    """Create indicator_insight nodes when winners diverge from overall population.

    For each indicator, computes the mean for winners vs losers.
    If the divergence is > 20% of the indicator's range, creates a node.
    """
    total = len(trades)
    if total < 3:
        return []

    winners = [t for t in trades if (t.get("pnl") or 0) > 0]
    losers = [t for t in trades if (t.get("pnl") or 0) <= 0]
    if not winners or not losers:
        return []

    # Collect flattened indicator values per outcome
    all_vals: dict[str, list[float]] = defaultdict(list)
    win_vals: dict[str, list[float]] = defaultdict(list)
    lose_vals: dict[str, list[float]] = defaultdict(list)

    for t in trades:
        entry_ind = t.get("entry_indicators") or t.get("variables_at_entry") or {}
        flat = _flatten_indicators(entry_ind)
        is_winner = (t.get("pnl") or 0) > 0
        for k, v in flat.items():
            all_vals[k].append(v)
            if is_winner:
                win_vals[k].append(v)
            else:
                lose_vals[k].append(v)

    nodes: list[SkillNode] = []

    for ind_name, values in all_vals.items():
        wv = win_vals.get(ind_name, [])
        lv = lose_vals.get(ind_name, [])
        if len(wv) < 2 or len(lv) < 2:
            continue

        val_range = max(values) - min(values)
        if val_range == 0:
            continue  # constant value, no insight

        win_mean = sum(wv) / len(wv)
        lose_mean = sum(lv) / len(lv)
        divergence = abs(win_mean - lose_mean)
        divergence_pct = divergence / val_range

        # Only create insight if divergence is meaningful (>20% of range)
        if divergence_pct < 0.20:
            continue

        # Determine direction of the insight
        if win_mean > lose_mean:
            direction = "higher"
            insight = f"Winners have {ind_name} avg {win_mean:.4g} vs losers {lose_mean:.4g}"
        else:
            direction = "lower"
            insight = f"Winners have {ind_name} avg {win_mean:.4g} vs losers {lose_mean:.4g}"

        # Compute win rate when indicator is in the "winning zone"
        # Winning zone: values closer to win_mean than lose_mean
        mid = (win_mean + lose_mean) / 2
        zone_trades = []
        for t in trades:
            entry_ind = t.get("entry_indicators") or t.get("variables_at_entry") or {}
            flat = _flatten_indicators(entry_ind)
            val = flat.get(ind_name)
            if val is None:
                continue
            if direction == "higher" and val >= mid:
                zone_trades.append(t)
            elif direction == "lower" and val <= mid:
                zone_trades.append(t)

        zone_total = len(zone_trades)
        zone_wins = sum(1 for t in zone_trades if (t.get("pnl") or 0) > 0)
        zone_wr = round(zone_wins / zone_total * 100, 1) if zone_total > 0 else 0

        confidence = _determine_confidence(zone_total, zone_wr)

        # Short readable indicator name
        short_name = ind_name.split(".")[-1] if "." in ind_name else ind_name
        prefix = ind_name.split(".")[0] if "." in ind_name else ""

        title = f"{prefix} {short_name} {direction} → {zone_wr}% WR (n={zone_total})"

        description_lines = [
            f"Indicator: {ind_name} | Symbol: {symbol} | TF: {timeframe}",
            f"Regime: {regime} | Phase: {phase}",
            f"",
            f"Winner mean: {win_mean:.4g} | Loser mean: {lose_mean:.4g}",
            f"Divergence: {divergence:.4g} ({divergence_pct:.0%} of range {min(values):.4g}..{max(values):.4g})",
            f"",
            f"When {ind_name} is {direction} (threshold {mid:.4g}):",
            f"  Win rate: {zone_wr}% | Trades: {zone_total} | Wins: {zone_wins}",
            f"",
            f"Insight: {insight}",
        ]

        node = SkillNode(
            category=SkillCategory.INDICATOR_INSIGHT,
            title=title,
            description="\n".join(description_lines),
            confidence=confidence,
            source_type="backtest",
            source_id=run_id,
            playbook_id=playbook_id,
            symbol=symbol,
            timeframe=timeframe,
            market_regime=regime,
            sample_size=zone_total,
            win_rate=zone_wr,
            avg_pnl=0,
            avg_rr=0,
            indicators_json={
                ind_name: {
                    "win_mean": round(win_mean, 4),
                    "lose_mean": round(lose_mean, 4),
                    "divergence_pct": round(divergence_pct * 100, 1),
                    "direction": direction,
                    "threshold": round(mid, 4),
                    "all_min": round(min(values), 4),
                    "all_max": round(max(values), 4),
                }
            },
            tags=[ind_name, regime, "indicator_insight", direction],
        )
        nodes.append(node)

    return nodes


def _determine_confidence(sample_size: int, win_rate: float) -> Confidence:
    if sample_size >= 10 and win_rate >= 60:
        return Confidence.HIGH
    if sample_size >= 5:
        return Confidence.MEDIUM
    return Confidence.LOW


def _categorize_group(phase: str, stats: dict) -> SkillCategory:
    """Determine the category based on phase and stats."""
    phase_lower = phase.lower()
    if "entry" in phase_lower or "trigger" in phase_lower:
        return SkillCategory.ENTRY_PATTERN
    if "exit" in phase_lower or "close" in phase_lower:
        return SkillCategory.EXIT_SIGNAL
    if "regime" in phase_lower or "filter" in phase_lower:
        return SkillCategory.REGIME_FILTER
    if stats["win_rate"] < 40 and stats["total"] >= 5:
        return SkillCategory.RISK_INSIGHT
    return SkillCategory.ENTRY_PATTERN


def _generate_title_template(
    category: SkillCategory,
    regime: str,
    phase: str,
    symbol: str,
    stats: dict,
) -> str:
    wr = stats["win_rate"]
    n = stats["total"]

    if category == SkillCategory.ENTRY_PATTERN:
        return f"{phase} entries in {regime} — {wr}% WR ({n} trades)"
    if category == SkillCategory.EXIT_SIGNAL:
        return f"{phase} exits in {regime} — avg RR {stats['avg_rr']}"
    if category == SkillCategory.REGIME_FILTER:
        return f"{regime} regime — {wr}% WR across {n} trades"
    if category == SkillCategory.RISK_INSIGHT:
        return f"Weak: {phase} in {regime} — only {wr}% WR ({n} trades)"
    return f"{phase} pattern in {regime} — {wr}% WR"


def _generate_description_template(
    category: SkillCategory,
    regime: str,
    phase: str,
    symbol: str,
    timeframe: str,
    stats: dict,
    indicators: dict,
) -> str:
    lines = [
        f"Symbol: {symbol} | Timeframe: {timeframe} | Regime: {regime} | Phase: {phase}",
        f"Sample: {stats['total']} trades | Wins: {stats['wins']} | Losses: {stats['losses']}",
        f"Win Rate: {stats['win_rate']}% | Avg PnL: {stats['avg_pnl']} | Avg RR: {stats['avg_rr']}",
        f"Best: {stats['best_pnl']} | Worst: {stats['worst_pnl']} | Total PnL: {stats['total_pnl']}",
    ]

    if indicators:
        lines.append("")
        lines.append("Indicator ranges at entry:")
        for name, ranges in list(indicators.items())[:8]:
            parts = [f"all: {ranges['all_min']}..{ranges['all_max']} (mean {ranges['all_mean']})"]
            if "win_mean" in ranges:
                parts.append(f"winners: {ranges['win_min']}..{ranges['win_max']} (mean {ranges['win_mean']})")
            lines.append(f"  {name}: {' | '.join(parts)}")

    if category == SkillCategory.RISK_INSIGHT:
        lines.append("")
        lines.append(f"WARNING: Low win rate ({stats['win_rate']}%) — consider filtering or avoiding this setup.")

    return "\n".join(lines)


async def _find_overlapping_nodes(
    db: Database,
    node: SkillNode,
    batch_nodes: list[SkillNode],
) -> list[SkillNode]:
    """Find nodes that overlap with this one (same symbol + regime + similar indicators)."""
    overlapping = []

    # Check within the current batch
    for other in batch_nodes:
        if other.id == node.id:
            continue
        # Same symbol + regime, but different category or source
        if (other.symbol == node.symbol
                and other.market_regime == node.market_regime
                and other.id != node.id):
            # Skip indicator<->indicator edges within same group (already linked via parent)
            if (node.category == SkillCategory.INDICATOR_INSIGHT
                    and other.category == SkillCategory.INDICATOR_INSIGHT
                    and node.source_id == other.source_id):
                continue
            overlapping.append(other)

    # Check existing nodes in DB with same symbol and regime
    existing = await db.list_skill_nodes(
        symbol=node.symbol,
        market_regime=node.market_regime,
        limit=50,
    )
    for existing_node in existing:
        if existing_node.id == node.id:
            continue
        if existing_node.source_id == node.source_id:
            continue  # skip same-backtest nodes already in batch
        overlapping.append(existing_node)

    return overlapping


def _compute_edge_relationship(
    node_a: SkillNode,
    node_b: SkillNode,
) -> tuple[EdgeRelationship, float, str]:
    """Determine the relationship between two overlapping nodes."""
    wr_diff = abs(node_a.win_rate - node_b.win_rate)

    # Indicator insight connected to same indicator from another source
    if (node_a.category == SkillCategory.INDICATOR_INSIGHT
            and node_b.category == SkillCategory.INDICATOR_INSIGHT):
        # Check if same indicator
        a_inds = set((node_a.indicators_json or {}).keys())
        b_inds = set((node_b.indicators_json or {}).keys())
        if a_inds & b_inds:
            # Same indicator across backtests — check if directions agree
            shared = (a_inds & b_inds).pop()
            a_dir = (node_a.indicators_json or {}).get(shared, {}).get("direction")
            b_dir = (node_b.indicators_json or {}).get(shared, {}).get("direction")
            if a_dir == b_dir:
                return (
                    EdgeRelationship.SUPPORTS,
                    round(0.8 + min(wr_diff, 20) / 100, 2),
                    f"Same indicator ({shared}), same direction ({a_dir})",
                )
            else:
                return (
                    EdgeRelationship.CONTRADICTS,
                    0.9,
                    f"Same indicator ({shared}), opposite direction ({a_dir} vs {b_dir})",
                )

    # Same category with similar win rates = supports
    if node_a.category == node_b.category:
        if wr_diff < 10:
            weight = 1.0 - (wr_diff / 100)
            return (
                EdgeRelationship.SUPPORTS,
                round(weight, 2),
                f"Same category, similar WR (diff {wr_diff:.1f}%)",
            )
        else:
            return (
                EdgeRelationship.REFINES,
                round(0.5 + wr_diff / 200, 2),
                f"Same category, divergent WR (diff {wr_diff:.1f}%)",
            )

    # One is a risk insight (low WR) contradicting a pattern
    if node_a.category == SkillCategory.RISK_INSIGHT or node_b.category == SkillCategory.RISK_INSIGHT:
        return (
            EdgeRelationship.CONTRADICTS,
            0.8,
            "Risk insight vs pattern — conflicting signals",
        )

    # Different categories in same regime = combines_with
    return (
        EdgeRelationship.COMBINES_WITH,
        0.7,
        f"Different categories ({node_a.category.value} + {node_b.category.value}) in same regime",
    )
