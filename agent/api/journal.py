"""Trade Journal API routes — view journal entries and analytics."""

from fastapi import APIRouter, HTTPException

from agent.api.main import app_state

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("")
async def list_journal_entries(
    playbook_id: int | None = None,
    strategy_id: int | None = None,
    symbol: str | None = None,
    outcome: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List trade journal entries with optional filters."""
    db = app_state["db"]
    entries = await db.list_journal_entries(
        playbook_db_id=playbook_id,
        strategy_id=strategy_id,
        symbol=symbol,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": e.id,
            "trade_id": e.trade_id,
            "playbook_db_id": e.playbook_db_id,
            "symbol": e.symbol,
            "direction": e.direction,
            "lot_initial": e.lot_initial,
            "lot_remaining": e.lot_remaining,
            "open_price": e.open_price,
            "close_price": e.close_price,
            "sl_initial": e.sl_initial,
            "tp_initial": e.tp_initial,
            "sl_final": e.sl_final,
            "tp_final": e.tp_final,
            "open_time": str(e.open_time) if e.open_time else None,
            "close_time": str(e.close_time) if e.close_time else None,
            "duration_seconds": e.duration_seconds,
            "bars_held": e.bars_held,
            "pnl": e.pnl,
            "pnl_pips": e.pnl_pips,
            "rr_achieved": e.rr_achieved,
            "outcome": e.outcome,
            "exit_reason": e.exit_reason,
            "playbook_phase_at_entry": e.playbook_phase_at_entry,
            "management_events_count": len(e.management_events),
            "created_at": str(e.created_at) if e.created_at else None,
        }
        for e in entries
    ]


@router.get("/analytics")
async def get_journal_analytics(
    playbook_id: int | None = None,
    strategy_id: int | None = None,
    symbol: str | None = None,
):
    """Get aggregate journal analytics."""
    db = app_state["db"]
    return await db.get_journal_analytics(
        playbook_db_id=playbook_id,
        strategy_id=strategy_id,
        symbol=symbol,
    )


@router.get("/analytics/conditions")
async def get_condition_analytics(playbook_id: int | None = None):
    """Get per-condition win rates from journal data."""
    db = app_state["db"]
    return await db.get_journal_condition_analytics(playbook_db_id=playbook_id)


@router.get("/{journal_id}")
async def get_journal_entry(journal_id: int):
    """Get a single journal entry with full snapshots."""
    db = app_state["db"]
    entry = await db.get_journal_entry(journal_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return entry.model_dump(mode="json")
