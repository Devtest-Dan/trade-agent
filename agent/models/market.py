from pydantic import BaseModel
from datetime import datetime
from typing import Any


class Tick(BaseModel):
    symbol: str
    bid: float
    ask: float
    spread: float
    timestamp: datetime


class Bar(BaseModel):
    symbol: str
    timeframe: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class IndicatorValue(BaseModel):
    indicator_id: str
    name: str
    symbol: str
    timeframe: str
    params: dict[str, Any]
    values: dict[str, float]  # e.g. {"value": 28.3} or {"k": 45.2, "d": 42.1}
    bar_time: datetime


class MarketSnapshot(BaseModel):
    symbol: str
    timeframe: str
    tick: Tick | None = None
    bars: list[Bar] = []
    indicators: dict[str, IndicatorValue] = {}  # keyed by indicator_id
