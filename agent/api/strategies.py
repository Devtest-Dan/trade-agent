"""Strategy CRUD endpoints + AI parsing + AI chat."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent.api.auth import get_current_user
from agent.models.strategy import Autonomy, Strategy, StrategyConfig

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class CreateStrategyRequest(BaseModel):
    description: str  # natural language


class UpdateStrategyRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    enabled: bool | None = None


class SetAutonomyRequest(BaseModel):
    autonomy: Autonomy


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


def get_app_state(request):
    """Helper to access app state from request."""
    from agent.api.main import app_state
    return app_state


@router.post("")
async def create_strategy(
    req: CreateStrategyRequest, user: str = Depends(get_current_user)
):
    """Parse natural language strategy via AI and create it."""
    from agent.api.main import app_state

    ai = app_state["ai_service"]
    db = app_state["db"]

    try:
        config = await ai.parse_strategy(req.description)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse strategy: {e}")

    strategy = Strategy(
        name=config.name,
        description_nl=req.description,
        config=config,
        enabled=False,
    )

    sid = await db.create_strategy(strategy)
    strategy.id = sid

    # Load into engine (disabled until user enables)
    engine = app_state["strategy_engine"]
    engine.load_strategy(strategy)

    return {
        "id": sid,
        "name": config.name,
        "config": config.model_dump(),
        "message": "Strategy parsed. Review the config and enable when ready.",
    }


@router.get("")
async def list_strategies(user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    strategies = await app_state["db"].list_strategies()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description_nl,
            "autonomy": s.config.autonomy.value,
            "enabled": s.enabled,
            "symbols": s.config.symbols,
            "timeframes": s.config.timeframes_used,
            "created_at": str(s.created_at) if s.created_at else None,
        }
        for s in strategies
    ]


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: int, user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    strategy = await app_state["db"].get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description_nl,
        "config": strategy.config.model_dump(),
        "enabled": strategy.enabled,
        "created_at": str(strategy.created_at) if strategy.created_at else None,
    }


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: int,
    req: UpdateStrategyRequest,
    user: str = Depends(get_current_user),
):
    from agent.api.main import app_state
    db = app_state["db"]

    strategy = await db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.config is not None:
        updates["config"] = StrategyConfig(**req.config)
    if req.enabled is not None:
        updates["enabled"] = req.enabled

    await db.update_strategy(strategy_id, **updates)

    # Reload in engine
    updated = await db.get_strategy(strategy_id)
    if updated:
        app_state["strategy_engine"].load_strategy(updated)

    return {"success": True}


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: int, user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    app_state["strategy_engine"].unload_strategy(strategy_id)
    await app_state["db"].delete_strategy(strategy_id)
    return {"success": True}


@router.put("/{strategy_id}/autonomy")
async def set_autonomy(
    strategy_id: int,
    req: SetAutonomyRequest,
    user: str = Depends(get_current_user),
):
    from agent.api.main import app_state
    db = app_state["db"]

    strategy = await db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    strategy.config.autonomy = req.autonomy
    await db.update_strategy(strategy_id, config=strategy.config, autonomy=req.autonomy)

    # Reload in engine
    updated = await db.get_strategy(strategy_id)
    if updated:
        app_state["strategy_engine"].load_strategy(updated)

    return {"success": True, "autonomy": req.autonomy.value}


@router.put("/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: int, user: str = Depends(get_current_user)):
    from agent.api.main import app_state
    db = app_state["db"]

    strategy = await db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    new_enabled = not strategy.enabled
    await db.update_strategy(strategy_id, enabled=new_enabled)

    updated = await db.get_strategy(strategy_id)
    if updated:
        if new_enabled:
            app_state["strategy_engine"].load_strategy(updated)
            # Initialize data for strategy timeframes
            dm = app_state["data_manager"]
            for symbol in updated.config.symbols:
                await dm.initialize(symbol, updated.config.timeframes_used)
        else:
            app_state["strategy_engine"].unload_strategy(strategy_id)

    return {"success": True, "enabled": new_enabled}


@router.post("/{strategy_id}/chat")
async def chat_strategy(
    strategy_id: int,
    req: ChatRequest,
    user: str = Depends(get_current_user),
):
    """Multi-turn AI chat about a specific strategy."""
    from agent.api.main import app_state

    ai = app_state["ai_service"]
    db = app_state["db"]

    strategy = await db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    try:
        reply = await ai.chat_strategy(
            config=strategy.config.model_dump(),
            messages=messages,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI chat failed: {e}")

    return {"reply": reply}
