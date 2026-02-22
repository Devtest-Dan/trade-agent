"""Pydantic models for backtesting."""

from pydantic import BaseModel
from typing import Any


class BacktestConfig(BaseModel):
    playbook_id: int
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    bar_count: int = 500
    spread_pips: float = 0.3
    slippage_pips: float = 0.0
    commission_per_lot: float = 0.0  # round-trip commission in account currency per lot
    starting_balance: float = 10000.0
    start_date: str | None = None  # ISO date string, e.g. "2024-01-01"
    end_date: str | None = None    # ISO date string, e.g. "2024-12-31"


class BacktestTrade(BaseModel):
    direction: str  # BUY or SELL
    open_idx: int
    close_idx: int
    open_price: float
    close_price: float
    open_time: str = ""
    close_time: str = ""
    sl: float | None = None
    tp: float | None = None
    lot: float = 0.1
    pnl: float = 0.0
    pnl_pips: float = 0.0
    commission: float = 0.0
    rr_achieved: float | None = None
    outcome: str = ""  # win, loss, breakeven
    exit_reason: str = ""  # sl, tp, transition, timeout, end_of_data
    phase_at_entry: str = ""
    variables_at_entry: dict[str, Any] = {}
    entry_indicators: dict[str, Any] = {}
    fired_rules: list[dict[str, Any]] = []  # per-rule results from evaluate_condition_detailed
    fired_transition: str = ""  # transition name that opened the trade
    market_regime: str = ""  # trending, ranging, volatile, quiet


class BacktestMetrics(BaseModel):
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    recovery_factor: float = 0.0
    avg_rr: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    avg_duration_bars: float = 0.0
    # New metrics
    cagr: float = 0.0
    calmar_ratio: float = 0.0
    ulcer_index: float = 0.0
    expectancy: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0
    best_trade_streak_pnl: float = 0.0
    worst_trade_streak_pnl: float = 0.0
    monthly_returns: dict[str, float] = {}
    win_rate_long: float = 0.0
    win_rate_short: float = 0.0
    avg_bars_winners: float = 0.0
    avg_bars_losers: float = 0.0


class BacktestResult(BaseModel):
    config: BacktestConfig
    metrics: BacktestMetrics
    equity_curve: list[float] = []
    drawdown_curve: list[float] = []
    trades: list[BacktestTrade] = []


class BacktestRun(BaseModel):
    id: int | None = None
    playbook_id: int
    symbol: str
    timeframe: str
    bar_count: int
    status: str = "pending"
    config: BacktestConfig | None = None
    result: BacktestResult | None = None
    created_at: str | None = None
