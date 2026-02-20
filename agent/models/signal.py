from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Any


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"


class SignalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


class Signal(BaseModel):
    id: int | None = None
    strategy_id: int
    playbook_db_id: int | None = None
    playbook_phase: str = ""
    strategy_name: str = ""
    symbol: str
    direction: SignalDirection
    conditions_snapshot: dict[str, Any] = {}
    ai_reasoning: str = ""
    status: SignalStatus = SignalStatus.PENDING
    price_at_signal: float = 0.0
    created_at: datetime | None = None
