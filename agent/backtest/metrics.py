"""Backtest metrics computation — Sharpe, drawdown, profit factor, etc."""

import math

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

    # Sortino ratio (only downside deviation)
    if len(returns) > 1:
        downside = [r for r in returns if r < 0]
        if downside:
            down_dev = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
            sortino = (mean_ret / down_dev * math.sqrt(252)) if down_dev > 0 else 0.0
        else:
            sortino = 999.0 if mean_ret > 0 else 0.0
    else:
        sortino = 0.0

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
    )
