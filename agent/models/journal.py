"""Trade Journal models — full trade context capture for learning and refinement."""

from pydantic import BaseModel
from datetime import datetime
from typing import Any, Literal


class MarketContext(BaseModel):
    """Market conditions at the time of trade entry or exit."""
    atr: float | None = None
    atr_timeframe: str = "H1"
    session: str = ""  # "london", "newyork", "asian", "overlap"
    volatility: str = ""  # "low", "normal", "high", "extreme"
    trend: str = ""  # "bullish", "bearish", "ranging"
    spread: float | None = None


class ManagementEvent(BaseModel):
    """A single position management event (SL move, partial close, trail)."""
    time: datetime
    rule_name: str
    action: str  # "modify_sl", "modify_tp", "trail_sl", "partial_close"
    details: dict[str, Any] = {}  # e.g. {"old_sl": 2710.5, "new_sl": 2715.0}
    phase: str = ""


class TradeJournalEntry(BaseModel):
    """Complete trade journal entry with full context."""
    id: int | None = None
    trade_id: int | None = None
    signal_id: int | None = None
    strategy_id: int | None = None
    playbook_db_id: int | None = None

    # Trade details
    symbol: str
    direction: Literal["BUY", "SELL"]
    lot_initial: float
    lot_remaining: float | None = None

    # Prices
    open_price: float
    signal_price: float | None = None  # price when signal was generated
    fill_price: float | None = None  # actual fill from MT5
    slippage_pips: float | None = None  # adverse slippage in pips
    close_price: float | None = None
    sl_initial: float | None = None
    tp_initial: float | None = None
    sl_final: float | None = None
    tp_final: float | None = None

    # Timing
    open_time: datetime | None = None
    close_time: datetime | None = None
    duration_seconds: int | None = None
    bars_held: int | None = None

    # Outcome
    pnl: float | None = None
    pnl_pips: float | None = None
    rr_achieved: float | None = None
    outcome: str | None = None  # "win", "loss", "breakeven"
    exit_reason: str | None = None  # "tp_hit", "sl_hit", "manual", "signal_exit", "structure_reversal", "timeout", "kill_switch"

    # Playbook context
    playbook_phase_at_entry: str | None = None
    variables_at_entry: dict[str, Any] = {}

    # Snapshots
    entry_snapshot: dict[str, Any] = {}  # all indicator values at entry
    exit_snapshot: dict[str, Any] = {}  # all indicator values at exit
    entry_conditions: dict[str, Any] = {}  # which rules fired
    exit_conditions: dict[str, Any] = {}  # which rules fired
    market_context: MarketContext | None = None
    management_events: list[ManagementEvent] = []

    created_at: datetime | None = None
