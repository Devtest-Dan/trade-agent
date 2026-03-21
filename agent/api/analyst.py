"""Continuous Analyst API routes — start/stop/configure the live market analyst."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent.api.auth import get_current_user

router = APIRouter(prefix="/api/analyst", tags=["analyst"])


# ── Request/Response Models ──────────────────────────────────────────

class AnalystStartRequest(BaseModel):
    symbols: list[str] = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    timeframes: list[str] = ["M15", "H1", "H4", "D1"]
    interval_seconds: int = 300
    model: str = "opus"
    model_per_symbol: str = "opus"
    model_review: str = "opus"
    multi_symbol_mode: str = "individual"
    two_pass_enabled: bool = True


class AnalystConfigUpdate(BaseModel):
    symbols: list[str] | None = None
    timeframes: list[str] | None = None
    interval_seconds: int | None = None
    model: str | None = None
    model_per_symbol: str | None = None
    model_review: str | None = None
    multi_symbol_mode: str | None = None
    two_pass_enabled: bool | None = None
    adaptive_enabled: bool | None = None
    interval_alert: int | None = None
    interval_approach: int | None = None
    interval_nearby: int | None = None
    interval_coast: int | None = None
    interval_quiet: int | None = None


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
        symbols=req.symbols,
        timeframes=req.timeframes,
        interval_seconds=req.interval_seconds,
        model=req.model,
        model_per_symbol=req.model_per_symbol,
        model_review=req.model_review,
        multi_symbol_mode=req.multi_symbol_mode,
        two_pass_enabled=req.two_pass_enabled,
    )

    await analyst.start()
    return {
        "status": "started",
        "symbols": req.symbols,
        "timeframes": req.timeframes,
        "interval_seconds": req.interval_seconds,
        "model": req.model,
        "model_per_symbol": req.model_per_symbol,
        "model_review": req.model_review,
        "multi_symbol_mode": req.multi_symbol_mode,
        "two_pass_enabled": req.two_pass_enabled,
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
async def analyze_once(symbol: str | None = None, user: str = Depends(get_current_user)):
    """Run a single analysis on-demand. Pass ?symbol=XAUUSD for one symbol, or omit for all."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    if not app_state.get("mt5_connected"):
        raise HTTPException(status_code=503, detail="MT5 not connected")

    result = await analyst.analyze_once(symbol)
    if not result:
        raise HTTPException(status_code=500, detail="Analysis failed — no data")

    if isinstance(result, list):
        return {"count": len(result), "opinions": [_opinion_to_dict(op) for op in result]}
    return _opinion_to_dict(result)


@router.get("/latest")
async def get_latest_opinion(symbol: str | None = None, user: str = Depends(get_current_user)):
    """Get the most recent opinion. Pass ?symbol=XAUUSD for a specific symbol."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    if symbol:
        opinion = analyst.latest_opinion_for(symbol)
    else:
        opinion = analyst.latest_opinion

    if not opinion:
        raise HTTPException(status_code=404, detail="No analysis yet")

    return _opinion_to_dict(opinion)


@router.get("/history")
async def get_opinion_history(symbol: str | None = None, user: str = Depends(get_current_user)):
    """Get recent opinion history. Pass ?symbol=XAUUSD to filter by symbol."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    if symbol:
        opinions = analyst.opinions_for(symbol)
    else:
        opinions = analyst.opinions

    return {
        "count": len(opinions),
        "symbols": list(analyst._opinions_by_symbol.keys()),
        "opinions": [_opinion_to_dict(op) for op in opinions],
    }


@router.get("/status")
async def get_analyst_status(user: str = Depends(get_current_user)):
    """Get current analyst status and config."""
    from agent.api.main import app_state

    analyst = app_state.get("analyst")
    if not analyst:
        raise HTTPException(status_code=500, detail="Analyst not initialized")

    latest = analyst.latest_opinion

    # Per-symbol status summary
    per_symbol = {}
    for sym, opinions in analyst._opinions_by_symbol.items():
        if opinions:
            op = opinions[-1]
            per_symbol[sym] = {
                "bias": op.bias,
                "confidence": op.confidence,
                "urgency": op.urgency,
                "next_interval": op.next_interval,
                "timestamp": op.timestamp.isoformat(),
            }

    return {
        "running": analyst.running,
        "symbols": analyst.config.symbols,
        "timeframes": analyst.config.timeframes,
        "interval_seconds": analyst.config.interval_seconds,
        "model": analyst.config.model,
        "model_per_symbol": analyst.config.model_per_symbol,
        "multi_symbol_mode": analyst.config.multi_symbol_mode,
        "adaptive_enabled": analyst.config.adaptive_enabled,
        "total_opinions": len(analyst.opinions),
        "symbols_tracked": list(analyst._opinions_by_symbol.keys()),
        "per_symbol": per_symbol,
        "latest_bias": latest.bias if latest else None,
        "latest_confidence": latest.confidence if latest else None,
        "latest_timestamp": latest.timestamp.isoformat() if latest else None,
        "latest_urgency": latest.urgency if latest else None,
        "latest_next_interval": latest.next_interval if latest else None,
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
        "symbols": analyst.config.symbols,
        "timeframes": analyst.config.timeframes,
        "interval_seconds": analyst.config.interval_seconds,
        "model": analyst.config.model,
        "model_per_symbol": analyst.config.model_per_symbol,
        "multi_symbol_mode": analyst.config.multi_symbol_mode,
    }


# ── Feedback Routes ──────────────────────────────────────────────────

@router.get("/accuracy")
async def get_accuracy_stats(symbol: str = "XAUUSD", user: str = Depends(get_current_user)):
    """Get analyst accuracy stats across time periods."""
    from agent.api.main import app_state

    feedback = app_state.get("analyst_feedback")
    if not feedback:
        raise HTTPException(status_code=500, detail="Feedback not initialized")

    stats = await feedback.get_accuracy_stats(symbol)
    return {"symbol": symbol, "stats": stats}


@router.get("/scored")
async def get_scored_opinions(symbol: str = "XAUUSD", limit: int = 20, user: str = Depends(get_current_user)):
    """Get recent scored opinions with outcomes."""
    from agent.api.main import app_state

    feedback = app_state.get("analyst_feedback")
    if not feedback:
        raise HTTPException(status_code=500, detail="Feedback not initialized")

    opinions = await feedback.get_scored_opinions(symbol, limit)
    return {"symbol": symbol, "count": len(opinions), "opinions": opinions}


@router.post("/score-now")
async def trigger_scoring(user: str = Depends(get_current_user)):
    """Manually trigger scoring of pending opinions."""
    from agent.api.main import app_state

    feedback = app_state.get("analyst_feedback")
    analyst = app_state.get("analyst")
    if not feedback or not analyst:
        raise HTTPException(status_code=500, detail="Feedback/analyst not initialized")

    if not app_state.get("mt5_connected"):
        raise HTTPException(status_code=503, detail="MT5 not connected")

    scored = await feedback.score_pending_opinions(analyst.bridge)
    return {"scored": scored}


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
        # Adaptive scheduling
        "urgency": opinion.urgency,
        "next_interval": opinion.next_interval,
        "nearest_level_distance": opinion.nearest_level_distance,
        "nearest_level_atr_multiple": opinion.nearest_level_atr_multiple,
        # Two-pass review
        "review_verdict": opinion.review_verdict,
        "revised_confidence": opinion.revised_confidence,
        "review_challenges": opinion.review.get("challenges", []) if opinion.review else [],
        "review_missed_risks": opinion.review.get("missed_risks", []) if opinion.review else [],
        "review_key_concern": opinion.review.get("key_concern", "") if opinion.review else "",
        "review_recommendation": opinion.review.get("final_recommendation", "") if opinion.review else "",
    }
