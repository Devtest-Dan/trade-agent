"""Signal feed and approve/reject endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from agent.api.auth import get_current_user
from agent.models.signal import SignalStatus

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
async def list_signals(
    strategy_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: str = Depends(get_current_user),
):
    from agent.api.main import app_state
    signals = await app_state["db"].list_signals(
        strategy_id=strategy_id, status=status, limit=limit, offset=offset
    )
    return [
        {
            "id": s.id,
            "strategy_id": s.strategy_id,
            "strategy_name": s.strategy_name,
            "symbol": s.symbol,
            "direction": s.direction.value,
            "status": s.status.value,
            "price_at_signal": s.price_at_signal,
            "ai_reasoning": s.ai_reasoning,
            "conditions_snapshot": s.conditions_snapshot,
            "created_at": str(s.created_at) if s.created_at else None,
        }
        for s in signals
    ]


@router.post("/{signal_id}/approve")
async def approve_signal(signal_id: int, user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    db = app_state["db"]

    signal = await db.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal.status != SignalStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Signal is already {signal.status.value}")

    strategy = await db.get_strategy(signal.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Execute the trade
    executor = app_state["trade_executor"]
    from agent.risk_manager import RiskDecision
    decision = RiskDecision(approved=True, reason="Manually approved")
    result = await executor.process_signal(signal, strategy, decision)

    await db.update_signal_status(signal_id, result.status, result.ai_reasoning)

    return {"success": True, "status": result.status.value}


@router.post("/{signal_id}/reject")
async def reject_signal(signal_id: int, user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    db = app_state["db"]

    signal = await db.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    await db.update_signal_status(signal_id, SignalStatus.REJECTED, "Manually rejected")
    return {"success": True}
