"""Auto-hypothesis generation from backtest results.

Scans trade data and metrics to suggest parameter/threshold adjustments
that might improve performance. Each hypothesis includes the observation,
suggested change, and expected impact.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from agent.backtest.models import BacktestMetrics, BacktestTrade


@dataclass
class Hypothesis:
    category: str  # "entry", "exit", "risk", "timing", "direction"
    observation: str
    suggestion: str
    confidence: str  # "high", "medium", "low"
    param_path: str | None = None  # e.g. "variables.rsi_threshold"
    current_value: float | None = None
    suggested_value: float | None = None


def generate_hypotheses(
    trades: list[BacktestTrade],
    metrics: BacktestMetrics,
    config: dict | None = None,
) -> list[Hypothesis]:
    """Analyze trades and metrics to generate improvement hypotheses."""
    if len(trades) < 5:
        return [Hypothesis(
            category="general",
            observation="Too few trades for meaningful analysis",
            suggestion="Run backtest on more data or loosen entry conditions",
            confidence="low",
        )]

    hypotheses: list[Hypothesis] = []

    winners = [t for t in trades if t.outcome == "win"]
    losers = [t for t in trades if t.outcome == "loss"]

    # --- Exit analysis ---
    _analyze_exits(trades, winners, losers, metrics, hypotheses)

    # --- Direction bias ---
    _analyze_direction(trades, hypotheses)

    # --- Duration analysis ---
    _analyze_duration(winners, losers, hypotheses)

    # --- Risk/reward ---
    _analyze_risk_reward(trades, winners, losers, metrics, hypotheses)

    # --- Phase analysis ---
    _analyze_phases(trades, hypotheses)

    # --- Streak analysis ---
    _analyze_streaks(trades, metrics, hypotheses)

    # --- Indicator value analysis ---
    _analyze_indicator_values(winners, losers, hypotheses)

    return hypotheses


def _analyze_exits(
    trades: list[BacktestTrade],
    winners: list[BacktestTrade],
    losers: list[BacktestTrade],
    metrics: BacktestMetrics,
    out: list[Hypothesis],
) -> None:
    """Analyze exit patterns."""
    sl_exits = [t for t in trades if t.exit_reason == "sl"]
    tp_exits = [t for t in trades if t.exit_reason == "tp"]
    transition_exits = [t for t in trades if t.exit_reason == "transition"]

    total = len(trades)
    sl_pct = len(sl_exits) / total * 100 if total else 0
    tp_pct = len(tp_exits) / total * 100 if total else 0

    # High SL hit rate suggests SL is too tight
    if sl_pct > 60:
        avg_sl_loss = statistics.mean([abs(t.pnl) for t in sl_exits]) if sl_exits else 0
        out.append(Hypothesis(
            category="exit",
            observation=f"{sl_pct:.0f}% of trades hit SL — stop loss may be too tight",
            suggestion=f"Widen SL by 20-30%. Avg SL loss is ${avg_sl_loss:.2f}",
            confidence="high",
        ))

    # Low TP hit rate — TP may be too ambitious
    if tp_pct < 20 and len(tp_exits) > 0 and total > 10:
        out.append(Hypothesis(
            category="exit",
            observation=f"Only {tp_pct:.0f}% of trades reach TP — target may be too ambitious",
            suggestion="Reduce TP distance by 20-30% or use a trailing stop",
            confidence="medium",
        ))

    # Many transition exits with unrealized profit
    if transition_exits:
        profitable_transitions = [t for t in transition_exits if t.pnl > 0]
        avg_pnl_trans = statistics.mean([t.pnl for t in transition_exits])
        if avg_pnl_trans < 0 and len(transition_exits) > 3:
            out.append(Hypothesis(
                category="exit",
                observation=f"Transition exits avg PnL is ${avg_pnl_trans:.2f} — phase transitions close losing positions",
                suggestion="Add minimum-profit or breakeven condition before transition close",
                confidence="medium",
            ))


def _analyze_direction(
    trades: list[BacktestTrade],
    out: list[Hypothesis],
) -> None:
    """Analyze directional bias."""
    buys = [t for t in trades if t.direction == "BUY"]
    sells = [t for t in trades if t.direction == "SELL"]

    if not buys or not sells:
        return

    buy_wr = len([t for t in buys if t.outcome == "win"]) / len(buys) * 100
    sell_wr = len([t for t in sells if t.outcome == "win"]) / len(sells) * 100

    buy_avg = statistics.mean([t.pnl for t in buys])
    sell_avg = statistics.mean([t.pnl for t in sells])

    diff = abs(buy_wr - sell_wr)
    if diff > 15:
        better = "BUY" if buy_wr > sell_wr else "SELL"
        worse = "SELL" if better == "BUY" else "BUY"
        out.append(Hypothesis(
            category="direction",
            observation=f"{better} win rate ({max(buy_wr, sell_wr):.0f}%) significantly outperforms {worse} ({min(buy_wr, sell_wr):.0f}%)",
            suggestion=f"Consider adding a trend filter to skip {worse} trades in this market regime, or tighten {worse} entry conditions",
            confidence="high" if diff > 25 else "medium",
        ))

    # One direction is consistently unprofitable
    if buy_avg < 0 and sell_avg > 0 and len(buys) > 5:
        out.append(Hypothesis(
            category="direction",
            observation=f"BUY trades avg ${buy_avg:.2f} while SELL trades avg ${sell_avg:.2f}",
            suggestion="Strongly tighten or disable BUY entries — market may be in a downtrend",
            confidence="high",
        ))
    elif sell_avg < 0 and buy_avg > 0 and len(sells) > 5:
        out.append(Hypothesis(
            category="direction",
            observation=f"SELL trades avg ${sell_avg:.2f} while BUY trades avg ${buy_avg:.2f}",
            suggestion="Strongly tighten or disable SELL entries — market may be in an uptrend",
            confidence="high",
        ))


def _analyze_duration(
    winners: list[BacktestTrade],
    losers: list[BacktestTrade],
    out: list[Hypothesis],
) -> None:
    """Analyze trade duration patterns."""
    if not winners or not losers:
        return

    win_durations = [t.close_idx - t.open_idx for t in winners]
    loss_durations = [t.close_idx - t.open_idx for t in losers]

    avg_win_dur = statistics.mean(win_durations)
    avg_loss_dur = statistics.mean(loss_durations)

    # Losers held much longer than winners
    if avg_loss_dur > avg_win_dur * 1.5 and len(losers) > 5:
        out.append(Hypothesis(
            category="timing",
            observation=f"Losing trades held avg {avg_loss_dur:.0f} bars vs winners at {avg_win_dur:.0f} bars",
            suggestion=f"Add a time-based exit after {int(avg_win_dur * 1.3)}-{int(avg_win_dur * 1.5)} bars to cut losers earlier",
            confidence="high",
        ))

    # Very short winning trades — possible scalping opportunity
    if avg_win_dur < 3 and len(winners) > 10:
        out.append(Hypothesis(
            category="timing",
            observation=f"Winners close very quickly (avg {avg_win_dur:.1f} bars) — momentum entries",
            suggestion="Consider tightening TP for faster profit capture or using a lower timeframe",
            confidence="low",
        ))


def _analyze_risk_reward(
    trades: list[BacktestTrade],
    winners: list[BacktestTrade],
    losers: list[BacktestTrade],
    metrics: BacktestMetrics,
    out: list[Hypothesis],
) -> None:
    """Analyze risk/reward patterns."""
    if not winners or not losers:
        return

    avg_win = statistics.mean([t.pnl for t in winners])
    avg_loss = statistics.mean([abs(t.pnl) for t in losers])

    # Avg win < avg loss — poor R:R
    if avg_win < avg_loss and avg_loss > 0:
        ratio = avg_win / avg_loss
        out.append(Hypothesis(
            category="risk",
            observation=f"Avg win (${avg_win:.2f}) < avg loss (${avg_loss:.2f}) — R:R ratio {ratio:.2f}",
            suggestion="Either widen TP or tighten SL to achieve at least 1:1 risk-reward",
            confidence="high",
        ))

    # R:R values on trades with SL/TP
    rr_trades = [t for t in trades if t.rr_achieved is not None]
    if len(rr_trades) > 10:
        rr_values = [t.rr_achieved for t in rr_trades]
        median_rr = statistics.median(rr_values)
        if median_rr < 0.5:
            out.append(Hypothesis(
                category="risk",
                observation=f"Median R:R achieved is {median_rr:.2f} — most trades close well below risk taken",
                suggestion="Increase TP distance or add trailing stop to capture more reward",
                confidence="medium",
            ))

    # High max drawdown
    if metrics.max_drawdown_pct > 30:
        out.append(Hypothesis(
            category="risk",
            observation=f"Max drawdown {metrics.max_drawdown_pct:.1f}% is dangerously high",
            suggestion="Reduce position size, tighten SL, or add a maximum-open-positions limit",
            confidence="high",
        ))


def _analyze_phases(
    trades: list[BacktestTrade],
    out: list[Hypothesis],
) -> None:
    """Analyze per-phase performance."""
    phase_trades: dict[str, list[BacktestTrade]] = {}
    for t in trades:
        phase = t.phase_at_entry or "unknown"
        phase_trades.setdefault(phase, []).append(t)

    if len(phase_trades) < 2:
        return

    phase_stats = {}
    for phase, pts in phase_trades.items():
        if len(pts) < 3:
            continue
        wins = len([t for t in pts if t.outcome == "win"])
        wr = wins / len(pts) * 100
        avg_pnl = statistics.mean([t.pnl for t in pts])
        phase_stats[phase] = {"count": len(pts), "win_rate": wr, "avg_pnl": avg_pnl}

    # Find underperforming phases
    for phase, stats in phase_stats.items():
        if stats["avg_pnl"] < 0 and stats["count"] >= 5:
            out.append(Hypothesis(
                category="entry",
                observation=f"Phase '{phase}' has negative avg PnL (${stats['avg_pnl']:.2f}, {stats['count']} trades, {stats['win_rate']:.0f}% WR)",
                suggestion=f"Review entry conditions for phase '{phase}' — add stricter filters or skip this phase",
                confidence="high" if stats["count"] >= 10 else "medium",
            ))


def _analyze_streaks(
    trades: list[BacktestTrade],
    metrics: BacktestMetrics,
    out: list[Hypothesis],
) -> None:
    """Analyze consecutive win/loss patterns."""
    if metrics.consecutive_losses >= 5:
        out.append(Hypothesis(
            category="risk",
            observation=f"Max {metrics.consecutive_losses} consecutive losses — extended losing streaks detected",
            suggestion="Add a circuit breaker (pause trading after N consecutive losses) or reduce position size during drawdowns",
            confidence="medium",
        ))


def _analyze_indicator_values(
    winners: list[BacktestTrade],
    losers: list[BacktestTrade],
    out: list[Hypothesis],
) -> None:
    """Compare indicator values at entry for winners vs losers."""
    if not winners or not losers or len(winners) < 5 or len(losers) < 5:
        return

    # Collect all indicator IDs that appear in both sets
    win_indicators: dict[str, dict[str, list[float]]] = {}
    loss_indicators: dict[str, dict[str, list[float]]] = {}

    for trade_list, target in [(winners, win_indicators), (losers, loss_indicators)]:
        for t in trade_list:
            for ind_id, values in (t.entry_indicators or {}).items():
                if ind_id not in target:
                    target[ind_id] = {}
                for field, val in values.items():
                    if isinstance(val, (int, float)) and val < 1e300:
                        target[ind_id].setdefault(field, []).append(float(val))

    # Compare means between winners and losers
    for ind_id in win_indicators:
        if ind_id not in loss_indicators:
            continue
        for field in win_indicators[ind_id]:
            if field not in loss_indicators[ind_id]:
                continue
            win_vals = win_indicators[ind_id][field]
            loss_vals = loss_indicators[ind_id][field]
            if len(win_vals) < 5 or len(loss_vals) < 5:
                continue

            win_mean = statistics.mean(win_vals)
            loss_mean = statistics.mean(loss_vals)

            # Only report if there's a meaningful difference (>10% relative)
            if win_mean == 0 and loss_mean == 0:
                continue
            denom = max(abs(win_mean), abs(loss_mean), 1e-9)
            rel_diff = abs(win_mean - loss_mean) / denom

            if rel_diff > 0.1:
                out.append(Hypothesis(
                    category="entry",
                    observation=f"{ind_id}.{field}: winners avg {win_mean:.2f} vs losers avg {loss_mean:.2f}",
                    suggestion=f"Consider filtering entries where {ind_id}.{field} is closer to {win_mean:.2f} (winning range)",
                    confidence="medium" if rel_diff > 0.2 else "low",
                    param_path=f"indicators.{ind_id}.{field}",
                    current_value=round(loss_mean, 4),
                    suggested_value=round(win_mean, 4),
                ))
