"""Playbook models — multi-phase execution state machines for trading strategies."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Literal
from enum import Enum

from agent.models.strategy import Autonomy, RiskConfig, IndicatorConfig


class DynamicExpr(BaseModel):
    """An expression that evaluates at runtime (e.g., 'ind.h4_atr.value * 1.5')."""
    expr: str


class CheckCondition(BaseModel):
    """A single condition check within a transition or management rule."""
    type: Literal["AND", "OR"] = "AND"
    rules: list["CheckRule"] = []


class CheckRule(BaseModel):
    """A rule that checks an expression against a value or another expression."""
    left: str  # e.g. "ind.m15_rsi.value", "_price", "var.initial_sl"
    operator: str  # "<", ">", "<=", ">=", "==", "!="
    right: str  # e.g. "30", "ind.h4_ema20.value", "_price"
    description: str = ""


class TransitionAction(BaseModel):
    """An action to perform when a transition fires."""
    # Only one of these should be set per action
    set_var: str | None = None
    expr: str | None = None
    open_trade: "TradeAction | None" = None
    close_trade: bool = False
    log: str | None = None


class TradeAction(BaseModel):
    """Parameters for opening a trade via playbook."""
    direction: Literal["BUY", "SELL"]
    lot: DynamicExpr | None = None  # defaults to risk.max_lot
    sl: DynamicExpr | None = None
    tp: DynamicExpr | None = None


class ModifySLAction(BaseModel):
    """Modify stop loss to a dynamic value."""
    expr: str


class TrailSLAction(BaseModel):
    """Trail stop loss based on conditions."""
    distance: DynamicExpr  # e.g. "ind.h4_atr.value * 1.0"
    step: DynamicExpr | None = None  # minimum move before trailing


class PartialCloseAction(BaseModel):
    """Close a percentage of the open position."""
    pct: float  # 0-100


class PositionManagementRule(BaseModel):
    """A rule for managing an open position (trailing, partial close, breakeven)."""
    name: str
    once: bool = False  # fire only once
    continuous: bool = False  # re-evaluate every bar
    when: CheckCondition
    # Only one action type per rule
    modify_sl: ModifySLAction | None = None
    modify_tp: ModifySLAction | None = None  # reuse same structure
    trail_sl: TrailSLAction | None = None
    partial_close: PartialCloseAction | None = None


class PhaseTimeout(BaseModel):
    """Timeout configuration for a phase."""
    bars: int
    timeframe: str
    to: str  # phase to transition to on timeout


class Transition(BaseModel):
    """A possible transition from one phase to another."""
    to: str  # target phase name
    conditions: CheckCondition
    actions: list[TransitionAction] = []
    priority: int = 0  # higher priority transitions checked first


class Phase(BaseModel):
    """A single phase in the playbook state machine."""
    evaluate_on: list[str] = []  # timeframes that trigger evaluation
    transitions: list[Transition] = []
    timeout: PhaseTimeout | None = None
    position_management: list[PositionManagementRule] = []
    on_trade_closed: "PhaseTransitionRef | None" = None
    description: str = ""


class PhaseTransitionRef(BaseModel):
    """Reference to a phase to transition to on event."""
    to: str


class PlaybookVariable(BaseModel):
    """A variable tracked across phases."""
    type: Literal["float", "int", "bool", "string"] = "float"
    default: Any = 0.0


class PlaybookConfig(BaseModel):
    """Full playbook configuration — the JSON schema for execution playbooks."""
    schema_version: str = Field(default="playbook-v1", alias="$schema")
    id: str
    name: str
    description: str = ""
    symbols: list[str] = ["XAUUSD"]
    autonomy: Autonomy = Autonomy.SIGNAL_ONLY
    indicators: list[IndicatorConfig] = []
    variables: dict[str, PlaybookVariable] = {}
    phases: dict[str, Phase] = {}
    initial_phase: str = "idle"
    risk: RiskConfig = RiskConfig()

    model_config = {"populate_by_name": True}


class Playbook(BaseModel):
    """A playbook with database metadata."""
    id: int | None = None
    name: str
    description_nl: str = ""  # original natural language
    explanation: str = ""  # AI-generated strategy explanation
    config: PlaybookConfig
    enabled: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaybookState(BaseModel):
    """Runtime state of a playbook instance."""
    playbook_id: int
    symbol: str
    current_phase: str = "idle"
    variables: dict[str, Any] = {}
    bars_in_phase: int = 0
    phase_timeframe_bars: dict[str, int] = {}  # bars counted per timeout TF
    fired_once_rules: list[str] = []  # management rules that already fired
    open_ticket: int | None = None  # MT5 ticket if position is open
    open_direction: str | None = None
    updated_at: datetime | None = None


# Rebuild forward refs
CheckCondition.model_rebuild()
