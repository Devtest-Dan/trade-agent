"""Pydantic models for backtesting."""

from pydantic import BaseModel
from typing import Any


class BacktestConfig(BaseModel):
    playbook_id: int
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    bar_count: int = 500
    spread_pips: float = 0.3
    starting_balance: float = 10000.0


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
    rr_achieved: float | None = None
    outcome: str = ""  # win, loss, breakeven
    exit_reason: str = ""  # sl, tp, transition, timeout, end_of_data
    phase_at_entry: str = ""
    variables_at_entry: dict[str, Any] = {}
    entry_indicators: dict[str, Any] = {}


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
