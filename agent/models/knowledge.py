"""Skill Graph models — atomic trading insights extracted from backtests."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class SkillCategory(str, Enum):
    ENTRY_PATTERN = "entry_pattern"
    EXIT_SIGNAL = "exit_signal"
    REGIME_FILTER = "regime_filter"
    INDICATOR_INSIGHT = "indicator_insight"
    RISK_INSIGHT = "risk_insight"
    COMBINATION = "combination"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EdgeRelationship(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    COMBINES_WITH = "combines_with"


class SkillNode(BaseModel):
    """An atomic trading insight stored in the skill graph."""
    id: int | None = None
    category: SkillCategory
    title: str
    description: str = ""
    confidence: Confidence = Confidence.LOW
    source_type: str = "backtest"  # backtest | manual
    source_id: int | None = None  # backtest run ID
    playbook_id: int | None = None
    symbol: str | None = None
    timeframe: str | None = None
    market_regime: str | None = None
    sample_size: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    avg_rr: float = 0.0
    indicators_json: dict[str, Any] | None = None
    tags: list[str] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SkillEdge(BaseModel):
    """A relationship between two skill nodes."""
    id: int | None = None
    source_id: int
    target_id: int
    relationship: EdgeRelationship
    weight: float = 1.0
    reason: str = ""
    created_at: datetime | None = None


class SkillNodeCreate(BaseModel):
    """Request body for creating a skill node manually."""
    category: SkillCategory
    title: str
    description: str = ""
    confidence: Confidence = Confidence.MEDIUM
    symbol: str | None = None
    timeframe: str | None = None
    market_regime: str | None = None
    sample_size: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    avg_rr: float = 0.0
    indicators_json: dict[str, Any] | None = None
    tags: list[str] | None = None


class SkillEdgeCreate(BaseModel):
    """Request body for creating an edge between skill nodes."""
    source_id: int
    target_id: int
    relationship: EdgeRelationship
    weight: float = 1.0
    reason: str = ""
