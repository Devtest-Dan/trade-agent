from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Literal
from enum import Enum


class Autonomy(str, Enum):
    SIGNAL_ONLY = "signal_only"
    SEMI_AUTO = "semi_auto"
    FULL_AUTO = "full_auto"


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker — auto-disables playbook after consecutive losses or errors."""
    max_consecutive_losses: int = 0  # 0 = disabled
    max_errors: int = 0  # 0 = disabled
    cooldown_minutes: int = 60  # auto-re-enable after cooldown (0 = manual reset only)


class RiskConfig(BaseModel):
    max_lot: float = 0.1
    max_daily_trades: int = 5
    max_drawdown_pct: float = 3.0
    max_open_positions: int = 2
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()


class IndicatorConfig(BaseModel):
    id: str
    name: str
    timeframe: str
    params: dict[str, Any] = {}


class Condition(BaseModel):
    indicator: str  # references indicator id
    field: str  # "value", "k", "d", "cross_above", "cross_below", etc.
    operator: str = ""  # "<", ">", "<=", ">=", "==", "" (for cross_* fields)
    value: float | None = None
    compare_to: str | None = None  # "price", "another_indicator_id"


class Rule(BaseModel):
    type: Literal["filter", "trigger"] = "filter"
    timeframe: str = ""
    description: str = ""
    condition: Condition


class ConditionGroup(BaseModel):
    type: Literal["AND", "OR"] = "AND"
    rules: list[Rule] = []


class StrategyConfig(BaseModel):
    id: str
    name: str
    description: str  # original natural language
    version: int = 1
    symbols: list[str] = ["XAUUSD"]
    autonomy: Autonomy = Autonomy.SIGNAL_ONLY
    risk: RiskConfig = RiskConfig()
    timeframes_used: list[str] = []
    indicators: list[IndicatorConfig] = []
    conditions: dict[str, ConditionGroup] = {
        "entry_long": ConditionGroup(),
        "exit_long": ConditionGroup(type="OR"),
        "entry_short": ConditionGroup(),
        "exit_short": ConditionGroup(type="OR"),
    }


class Strategy(BaseModel):
    id: int | None = None
    name: str
    description_nl: str  # natural language description
    config: StrategyConfig
    enabled: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
