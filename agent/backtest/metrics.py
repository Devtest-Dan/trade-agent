"""Backtest metrics computation — Sharpe, drawdown, profit factor, etc."""

import math
from collections import defaultdict

from agent.backtest.models import BacktestMetrics, BacktestTrade


def compute_drawdown_curve(equity_curve: list[float]) -> list[float]:
    """Compute drawdown curve (negative values) from equity curve."""
    if not equity_curve:
        return []
    peak = equity_curve[0]
    dd = []
    for val in equity_curve:
        if val > peak:
            peak = val
        dd.append(val - peak)  # negative when below peak
    return dd


def _compute_sortino(returns: list[float], mean_ret: float) -> float:
    """Sortino ratio — uses downside deviation relative to zero target.

    Downside deviation = sqrt(sum(min(r, 0)^2) / N) where N is total
    number of returns (not just negative ones). This correctly penalizes
    the frequency of negative returns, not just their magnitude.
    """
    if len(returns) < 2:
        return 0.0
    downside_sq = sum(min(r, 0.0) ** 2 for r in returns)
    down_dev = math.sqrt(downside_sq / len(returns))
    if down_dev <= 0:
        return 999.0 if mean_ret > 0 else 0.0
    return mean_ret / down_dev * math.sqrt(252)


def _compute_ulcer_index(equity_curve: list[float]) -> float:
    """Ulcer Index — RMS of percentage drawdowns from peak."""
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    dd_pct_sq_sum = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd_pct = ((val - peak) / peak * 100) if peak > 0 else 0.0
        dd_pct_sq_sum += dd_pct ** 2
    return math.sqrt(dd_pct_sq_sum / len(equity_curve))


def _compute_skewness(values: list[float]) -> float:
    """Sample skewness (Fisher)."""
    n = len(values)
    if n < 3:
        return 0.0
    mean = sum(values) / n
    m2 = sum((v - mean) ** 2 for v in values) / n
    m3 = sum((v - mean) ** 3 for v in values) / n
    if m2 <= 0:
        return 0.0
    return m3 / (m2 ** 1.5)


def _compute_kurtosis(values: list[float]) -> float:
    """Excess kurtosis (Fisher, = 0 for normal distribution)."""
    n = len(values)
    if n < 4:
        return 0.0
    mean = sum(values) / n
    m2 = sum((v - mean) ** 2 for v in values) / n
    m4 = sum((v - mean) ** 4 for v in values) / n
    if m2 <= 0:
        return 0.0
    return (m4 / (m2 ** 2)) - 3.0


def _compute_streak_pnl(trades: list[BacktestTrade]) -> tuple[float, float]:
    """Best and worst consecutive streak P&L."""
    if not trades:
        return 0.0, 0.0

    best_streak = 0.0
    worst_streak = 0.0
    current_streak = 0.0
    prev_winning = None

    for t in trades:
        winning = t.pnl > 0
        if prev_winning is None or winning == prev_winning:
            current_streak += t.pnl
        else:
            current_streak = t.pnl
        if current_streak > best_streak:
            best_streak = current_streak
        if current_streak < worst_streak:
            worst_streak = current_streak
        prev_winning = winning

    return best_streak, worst_streak


def _compute_monthly_returns(
    trades: list[BacktestTrade], starting_balance: float
) -> dict[str, float]:
    """Monthly P&L as percentage of starting balance. Key format: YYYY-MM."""
    monthly: dict[str, float] = defaultdict(float)
    for t in trades:
        if t.close_time:
            # close_time format varies — try to extract YYYY-MM
            month_key = t.close_time[:7]  # "2024-01" from "2024-01-15T..."
            if len(month_key) == 7 and "-" in month_key:
                monthly[month_key] += t.pnl
    # Convert to percentage
    if starting_balance > 0:
        return {k: round(v / starting_balance * 100, 2) for k, v in sorted(monthly.items())}
    return dict(sorted(monthly.items()))


def compute_metrics(
    trades: list[BacktestTrade],
    equity_curve: list[float],
    starting_balance: float,
) -> BacktestMetrics:
    """Compute comprehensive backtest metrics."""
    if not trades:
        return BacktestMetrics()

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    total_pnl = sum(t.pnl for t in trades)
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))

    # Win rate
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0

    # Profit factor
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    # Drawdown
    dd_curve = compute_drawdown_curve(equity_curve)
    max_drawdown = abs(min(dd_curve)) if dd_curve else 0.0
    peak_equity = max(equity_curve) if equity_curve else starting_balance
    max_drawdown_pct = (max_drawdown / peak_equity * 100) if peak_equity > 0 else 0.0

    # Recovery factor
    recovery_factor = total_pnl / max_drawdown if max_drawdown > 0 else 0.0

    # Returns for Sharpe/Sortino (per-trade returns)
    returns = [t.pnl for t in trades]
    mean_ret = sum(returns) / len(returns) if returns else 0.0

    # Sharpe ratio (annualized, assume ~252 trading days)
    if len(returns) > 1:
        std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1))
        sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0

    # Sortino ratio (fixed — uses all returns for downside deviation denominator)
    sortino = _compute_sortino(returns, mean_ret)

    # Average R:R
    rr_vals = [t.rr_achieved for t in trades if t.rr_achieved is not None]
    avg_rr = sum(rr_vals) / len(rr_vals) if rr_vals else 0.0

    # Average win/loss
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0

    # Largest win/loss
    largest_win = max((t.pnl for t in wins), default=0.0)
    largest_loss = min((t.pnl for t in losses), default=0.0)

    # Consecutive wins/losses
    max_con_wins = 0
    max_con_losses = 0
    cur_wins = 0
    cur_losses = 0
    for t in trades:
        if t.pnl > 0:
            cur_wins += 1
            cur_losses = 0
            max_con_wins = max(max_con_wins, cur_wins)
        elif t.pnl < 0:
            cur_losses += 1
            cur_wins = 0
            max_con_losses = max(max_con_losses, cur_losses)
        else:
            cur_wins = 0
            cur_losses = 0

    # Average duration in bars
    durations = [t.close_idx - t.open_idx for t in trades]
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    # --- New metrics ---

    # CAGR — compound annual growth rate
    ending_balance = starting_balance + total_pnl
    # Estimate years from trade timestamps or bar count
    cagr = 0.0
    if trades and trades[0].open_time and trades[-1].close_time:
        try:
            from datetime import datetime
            first = trades[0].open_time
            last = trades[-1].close_time
            # Parse ISO-ish timestamps
            t0 = datetime.fromisoformat(first.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last.replace("Z", "+00:00"))
            years = (t1 - t0).total_seconds() / (365.25 * 86400)
            if years > 0 and ending_balance > 0 and starting_balance > 0:
                cagr = ((ending_balance / starting_balance) ** (1.0 / years) - 1.0) * 100
        except (ValueError, TypeError):
            pass

    # Calmar ratio — CAGR / max drawdown %
    calmar = abs(cagr) / max_drawdown_pct if max_drawdown_pct > 0 else 0.0

    # Ulcer Index
    ulcer = _compute_ulcer_index(equity_curve)

    # Expectancy — average $ per trade
    expectancy = total_pnl / len(trades) if trades else 0.0

    # Skewness & Kurtosis of trade returns
    skew = _compute_skewness(returns)
    kurt = _compute_kurtosis(returns)

    # Best/worst streak P&L
    best_streak_pnl, worst_streak_pnl = _compute_streak_pnl(trades)

    # Monthly returns
    monthly = _compute_monthly_returns(trades, starting_balance)

    # Win rate by direction
    longs = [t for t in trades if t.direction == "BUY"]
    shorts = [t for t in trades if t.direction == "SELL"]
    win_rate_long = (len([t for t in longs if t.pnl > 0]) / len(longs) * 100) if longs else 0.0
    win_rate_short = (len([t for t in shorts if t.pnl > 0]) / len(shorts) * 100) if shorts else 0.0

    # Avg bars held for winners vs losers
    winner_durations = [t.close_idx - t.open_idx for t in wins]
    loser_durations = [t.close_idx - t.open_idx for t in losses]
    avg_bars_winners = sum(winner_durations) / len(winner_durations) if winner_durations else 0.0
    avg_bars_losers = sum(loser_durations) / len(loser_durations) if loser_durations else 0.0

    return BacktestMetrics(
        total_trades=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate=round(win_rate, 1),
        total_pnl=round(total_pnl, 2),
        max_drawdown=round(max_drawdown, 2),
        max_drawdown_pct=round(max_drawdown_pct, 1),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        profit_factor=round(profit_factor, 2),
        recovery_factor=round(recovery_factor, 2),
        avg_rr=round(avg_rr, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        largest_win=round(largest_win, 2),
        largest_loss=round(largest_loss, 2),
        consecutive_wins=max_con_wins,
        consecutive_losses=max_con_losses,
        avg_duration_bars=round(avg_duration, 1),
        cagr=round(cagr, 2),
        calmar_ratio=round(calmar, 2),
        ulcer_index=round(ulcer, 2),
        expectancy=round(expectancy, 2),
        skewness=round(skew, 2),
        kurtosis=round(kurt, 2),
        best_trade_streak_pnl=round(best_streak_pnl, 2),
        worst_trade_streak_pnl=round(worst_streak_pnl, 2),
        monthly_returns=monthly,
        win_rate_long=round(win_rate_long, 1),
        win_rate_short=round(win_rate_short, 1),
        avg_bars_winners=round(avg_bars_winners, 1),
        avg_bars_losers=round(avg_bars_losers, 1),
    )
