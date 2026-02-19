"""Global settings and kill switch endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agent.api.auth import get_current_user

router = APIRouter(prefix="/api", tags=["settings"])


class GlobalRiskSettings(BaseModel):
    max_total_lots: float | None = None
    max_account_drawdown_pct: float | None = None
    daily_loss_limit: float | None = None


@router.post("/kill-switch")
async def kill_switch(user: str = Depends(get_current_user)):
    """Emergency: close all positions, pause all strategies."""
    from agent.api.main import app_state

    risk = app_state["risk_manager"]
    executor = app_state["trade_executor"]
    db = app_state["db"]

    # Activate kill switch
    risk.activate_kill_switch()

    # Close all positions
    closed = await executor.execute_kill_switch()

    # Disable all strategies
    strategies = await db.list_strategies()
    for s in strategies:
        if s.enabled:
            await db.update_strategy(s.id, enabled=False)
            app_state["strategy_engine"].unload_strategy(s.id)

    return {
        "success": True,
        "positions_closed": closed,
        "strategies_paused": len([s for s in strategies if s.enabled]),
    }


@router.post("/kill-switch/deactivate")
async def deactivate_kill_switch(user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    app_state["risk_manager"].deactivate_kill_switch()
    return {"success": True}


@router.get("/settings")
async def get_settings(user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    risk = app_state["risk_manager"]
    bridge = app_state["bridge"]

    return {
        "kill_switch_active": risk.kill_switch_active,
        "max_total_lots": risk.max_total_lots,
        "max_account_drawdown_pct": risk.max_account_drawdown_pct,
        "daily_loss_limit": risk.daily_loss_limit,
        "mt5_connected": bridge.connected,
    }


@router.put("/settings")
async def update_settings(
    req: GlobalRiskSettings, user: str = Depends(get_current_user)
):
    from agent.api.main import app_state
    risk = app_state["risk_manager"]
    risk.update_global_limits(
        max_total_lots=req.max_total_lots,
        max_account_drawdown_pct=req.max_account_drawdown_pct,
        daily_loss_limit=req.daily_loss_limit,
    )
    return {"success": True}
