"""Global settings, kill switch, and AI configuration endpoints."""

import re
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agent.api.auth import get_current_user

router = APIRouter(prefix="/api", tags=["settings"])


class GlobalRiskSettings(BaseModel):
    max_total_lots: float | None = None
    max_account_drawdown_pct: float | None = None
    daily_loss_limit: float | None = None
    anthropic_api_key: str | None = None


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
    ai = app_state["ai_service"]

    # Mask API key — show only last 4 chars
    masked_key = ""
    if ai.api_key_set:
        raw = ai._api_key
        if len(raw) > 4:
            masked_key = "sk-ant-•••" + raw[-4:]
        else:
            masked_key = "••••"

    return {
        "kill_switch_active": risk.kill_switch_active,
        "max_total_lots": risk.max_total_lots,
        "max_account_drawdown_pct": risk.max_account_drawdown_pct,
        "daily_loss_limit": risk.daily_loss_limit,
        "mt5_connected": bridge.connected,
        # AI config
        "ai_provider": ai.provider,
        "api_key_set": ai.api_key_set,
        "api_key_masked": masked_key,
    }


@router.put("/settings")
async def update_settings(
    req: GlobalRiskSettings, user: str = Depends(get_current_user)
):
    from agent.api.main import app_state
    risk = app_state["risk_manager"]

    # Update risk limits
    risk.update_global_limits(
        max_total_lots=req.max_total_lots,
        max_account_drawdown_pct=req.max_account_drawdown_pct,
        daily_loss_limit=req.daily_loss_limit,
    )

    # Update API key if provided
    if req.anthropic_api_key is not None:
        ai = app_state["ai_service"]
        ai.update_api_key(req.anthropic_api_key)
        _update_env_file("ANTHROPIC_API_KEY", req.anthropic_api_key)

    return {"success": True}


@router.post("/settings/test-ai")
async def test_ai(user: str = Depends(get_current_user)):
    """Quick test to verify AI connectivity."""
    from agent.api.main import app_state
    ai = app_state["ai_service"]

    try:
        text, usage = await ai._call(
            system="You are a test assistant.",
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            model="haiku",
            max_tokens=10,
        )
        return {
            "success": True,
            "provider": ai.provider,
            "response": text.strip(),
            "model": usage.get("model", "unknown"),
        }
    except Exception as e:
        return {
            "success": False,
            "provider": ai.provider,
            "error": str(e),
        }


def _update_env_file(key: str, value: str):
    """Update a key in the .env file (create if missing)."""
    env_path = Path(".env")

    if env_path.exists():
        content = env_path.read_text()
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + f"\n{key}={value}\n"
        env_path.write_text(content)
    else:
        env_path.write_text(f"{key}={value}\n")
