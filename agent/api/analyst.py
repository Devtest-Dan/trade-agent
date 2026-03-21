"""Continuous Analyst API routes — start/stop/configure the live market analyst."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent.api.auth import get_current_user

router = APIRouter(prefix="/api/analyst", tags=["analyst"])


# ── Request/Response Models ──────────────────────────────────────────

class AnalystStartRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframes: list[str] = ["M5", "M15", "H1", "H4", "D1"]
    interval_seconds: int = 300
    model: str = "sonnet"


class AnalystConfigUpdate(BaseModel):
    symbol: str | None = None
    timeframes: list[str] | None = None
    interval_seconds: int | None = None
    model: str | None = None


# ── Routes ───────────────────────────────────────────────────────────

@router.post("/start")
async def start_analyst(req: AnalystStartRequest, user: str = Depends(get_current_user)):
    """Start the continuous analyst loop."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    if analyst.running:
        raise HTTPException(status_code=409, detail="Analyst already running")

    if not app_state.get("mt5_connected"):
        raise HTTPException(status_code=503, detail="MT5 not connected")

    # Update config before starting
    analyst.update_config(
        symbol=req.symbol,
        timeframes=req.timeframes,
        interval_seconds=req.interval_seconds,
        model=req.model,
    )

    await analyst.start()
    return {
        "status": "started",
        "symbol": req.symbol,
        "timeframes": req.timeframes,
        "interval_seconds": req.interval_seconds,
        "model": req.model,
    }


@router.post("/stop")
async def stop_analyst(user: str = Depends(get_current_user)):
    """Stop the continuous analyst loop."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    if not analyst.running:
        raise HTTPException(status_code=409, detail="Analyst not running")

    await analyst.stop()
    return {"status": "stopped"}


@router.post("/analyze")
async def analyze_once(user: str = Depends(get_current_user)):
    """Run a single analysis on-demand (doesn't require the loop to be running)."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    if not app_state.get("mt5_connected"):
        raise HTTPException(status_code=503, detail="MT5 not connected")

    opinion = await analyst.analyze_once()
    if not opinion:
        raise HTTPException(status_code=500, detail="Analysis failed — no data")

    return _opinion_to_dict(opinion)


@router.get("/latest")
async def get_latest_opinion(user: str = Depends(get_current_user)):
    """Get the most recent analyst opinion."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    opinion = analyst.latest_opinion
    if not opinion:
        raise HTTPException(status_code=404, detail="No analysis yet")

    return _opinion_to_dict(opinion)


@router.get("/history")
async def get_opinion_history(user: str = Depends(get_current_user)):
    """Get the recent opinion history."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    return {
        "count": len(analyst.opinions),
        "opinions": [_opinion_to_dict(op) for op in analyst.opinions],
    }


@router.get("/status")
async def get_analyst_status(user: str = Depends(get_current_user)):
    """Get current analyst status and config."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    latest = analyst.latest_opinion
    return {
        "running": analyst.running,
        "symbol": analyst.config.symbol,
        "timeframes": analyst.config.timeframes,
        "interval_seconds": analyst.config.interval_seconds,
        "model": analyst.config.model,
        "opinions_count": len(analyst.opinions),
        "latest_bias": latest.bias if latest else None,
        "latest_confidence": latest.confidence if latest else None,
        "latest_timestamp": latest.timestamp.isoformat() if latest else None,
    }


@router.patch("/config")
async def update_analyst_config(req: AnalystConfigUpdate, user: str = Depends(get_current_user)):
    """Update analyst config (can be done while running)."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    analyst.update_config(**updates)

    return {
        "status": "updated",
        "symbol": analyst.config.symbol,
        "timeframes": analyst.config.timeframes,
        "interval_seconds": analyst.config.interval_seconds,
        "model": analyst.config.model,
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _opinion_to_dict(opinion) -> dict:
    """Convert AnalystOpinion to API response dict."""
    return {
        "timestamp": opinion.timestamp.isoformat(),
        "symbol": opinion.symbol,
        "current_price": opinion.current_price,
        "bias": opinion.bias,
        "confidence": opinion.confidence,
        "alignment": opinion.alignment,
        "trade_ideas": opinion.trade_ideas,
        "changes_from_last": opinion.changes_from_last,
        "computation_ms": opinion.computation_ms,
        "ai_model": opinion.ai_model,
        "timeframe_analysis": opinion.raw_response.get("timeframe_analysis", {}),
        "key_levels_above": opinion.raw_response.get("key_levels_above", []),
        "key_levels_below": opinion.raw_response.get("key_levels_below", []),
        "warnings": opinion.raw_response.get("warnings", []),
        "usage": opinion.usage,
    }
