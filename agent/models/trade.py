from pydantic import BaseModel
from datetime import datetime
from typing import Literal


class Trade(BaseModel):
    id: int | None = None
    signal_id: int | None = None
    strategy_id: int
    symbol: str
    direction: Literal["BUY", "SELL"]
    lot: float
    open_price: float
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
