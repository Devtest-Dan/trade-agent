from pydantic import BaseModel
from datetime import datetime
from typing import Literal


class Trade(BaseModel):
    id: int | None = None
    signal_id: int | None = None
    strategy_id: int
    playbook_db_id: int | None = None
    journal_id: int | None = None
    symbol: str
    direction: Literal["BUY", "SELL"]
    lot: float
    open_price: float  # actual fill price (from MT5 result)
    signal_price: float | None = None  # price when signal was generated
    fill_price: float | None = None  # actual fill price (alias for open_price, set from MT5)
    slippage_pips: float | None = None  # fill_price - signal_price in pips (adverse = positive)
    close_price: float | None = None
    sl: float | None = None
    tp: float | None = None
    pnl: float | None = None
    ticket: int | None = None  # MT5 order ticket
    open_time: datetime | None = None
    close_time: datetime | None = None


class Position(BaseModel):
    ticket: int
    symbol: str
    direction: Literal["BUY", "SELL"]
    lot: float
    open_price: float
    current_price: float
    sl: float | None = None
    tp: float | None = None
    pnl: float
    open_time: datetime


class AccountInfo(BaseModel):
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float | None = None
    profit: float = 0.0
