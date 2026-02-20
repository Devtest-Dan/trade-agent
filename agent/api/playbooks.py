"""Playbook API routes — build, manage, and refine execution playbooks."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.api.main import app_state

router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])


class BuildRequest(BaseModel):
    description: str


class RefineRequest(BaseModel):
    messages: list[dict]


class UpdateRequest(BaseModel):
    name: str | None = None
    description_nl: str | None = None
    config: dict | None = None
    autonomy: str | None = None


# --- Routes ---


@router.post("")
async def build_playbook(req: BuildRequest):
    """Build a new playbook from natural language description."""
    ai: "AIService" = app_state["ai_service"]
    db: "Database" = app_state["db"]

    try:
        result = await ai.build_playbook(req.description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playbook build failed: {e}")

    config = result["config"]

    # Save playbook to DB
    from agent.models.playbook import Playbook

    playbook = Playbook(
        name=config.name,
        description_nl=req.description,
        config=config,
        enabled=False,
    )
    playbook_id = await db.create_playbook(playbook)
    playbook.id = playbook_id

    # Save build session
    usage = result["usage"]
    await db.create_build_session(
        playbook_id=playbook_id,
        natural_language=req.description,
        skills_used=result["skills_used"],
        model_used=usage["model"],
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        duration_ms=usage["duration_ms"],
    )

    return {
        "id": playbook_id,
        "name": config.name,
        "config": config.model_dump(by_alias=True),
        "skills_used": result["skills_used"],
        "usage": usage,
    }


@router.get("")
async def list_playbooks():
    """List all playbooks."""
    db: "Database" = app_state["db"]
    playbooks = await db.list_playbooks()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description_nl": p.description_nl,
            "enabled": p.enabled,
            "autonomy": p.config.autonomy.value,
            "symbols": p.config.symbols,
            "phases": list(p.config.phases.keys()),
            "created_at": str(p.created_at) if p.created_at else None,
            "updated_at": str(p.updated_at) if p.updated_at else None,
        }
        for p in playbooks
    ]


@router.get("/{playbook_id}")
async def get_playbook(playbook_id: int):
    """Get a playbook with full config."""
    db: "Database" = app_state["db"]
    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return {
        "id": playbook.id,
        "name": playbook.name,
        "description_nl": playbook.description_nl,
        "config": playbook.config.model_dump(by_alias=True),
        "enabled": playbook.enabled,
        "created_at": str(playbook.created_at) if playbook.created_at else None,
        "updated_at": str(playbook.updated_at) if playbook.updated_at else None,
    }


@router.put("/{playbook_id}")
async def update_playbook(playbook_id: int, req: UpdateRequest):
    """Update a playbook's config or metadata."""
    db: "Database" = app_state["db"]
    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.description_nl is not None:
        updates["description_nl"] = req.description_nl
    if req.config is not None:
        from agent.models.playbook import PlaybookConfig
        updates["config"] = PlaybookConfig(**req.config)
    if req.autonomy is not None:
        updates["autonomy"] = req.autonomy

    await db.update_playbook(playbook_id, **updates)

    # Reload in engine if enabled
    engine = app_state.get("playbook_engine")
    if engine and playbook.enabled:
        updated = await db.get_playbook(playbook_id)
        engine.unload_playbook(playbook_id)
        if updated:
            engine.load_playbook(updated)

    return {"status": "updated"}


@router.delete("/{playbook_id}")
async def delete_playbook(playbook_id: int):
    """Delete a playbook."""
    db: "Database" = app_state["db"]
    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    # Unload from engine
    engine = app_state.get("playbook_engine")
    if engine:
        engine.unload_playbook(playbook_id)

    await db.delete_playbook(playbook_id)
    return {"status": "deleted"}


@router.put("/{playbook_id}/toggle")
async def toggle_playbook(playbook_id: int):
    """Enable or disable a playbook."""
    db: "Database" = app_state["db"]
    data_manager = app_state["data_manager"]
    engine = app_state.get("playbook_engine")

    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    new_enabled = not playbook.enabled
    await db.update_playbook(playbook_id, enabled=new_enabled)

    if engine:
        if new_enabled:
            playbook.enabled = True
            # Load saved state if exists
            state = None
            for symbol in playbook.config.symbols:
                state = await db.get_playbook_state(playbook_id, symbol)
                await data_manager.initialize(symbol, _get_playbook_timeframes(playbook.config))
            engine.load_playbook(playbook, state)
        else:
            engine.unload_playbook(playbook_id)

    return {"enabled": new_enabled}


@router.post("/{playbook_id}/refine")
async def refine_playbook(playbook_id: int, req: RefineRequest):
    """AI-assisted refinement using journal data."""
    ai: "AIService" = app_state["ai_service"]
    db: "Database" = app_state["db"]

    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    # Gather journal data
    analytics = await db.get_journal_analytics(playbook_db_id=playbook_id)
    conditions = await db.get_journal_condition_analytics(playbook_db_id=playbook_id)
    entries = await db.list_journal_entries(playbook_db_id=playbook_id, limit=20)
    samples = [e.model_dump(mode="json") for e in entries]

    result = await ai.refine_playbook(
        config=playbook.config.model_dump(by_alias=True),
        journal_analytics=analytics,
        condition_analytics=conditions,
        trade_samples=samples,
        messages=req.messages,
    )

    response = {"reply": result["reply"]}

    # If AI produced an updated config, save it
    if result["updated_config"]:
        await db.update_playbook(playbook_id, config=result["updated_config"])
        response["updated"] = True
        response["config"] = result["updated_config"].model_dump(by_alias=True)

        # Reload in engine if enabled
        engine = app_state.get("playbook_engine")
        if engine and playbook.enabled:
            engine.unload_playbook(playbook_id)
            updated = await db.get_playbook(playbook_id)
            if updated:
                engine.load_playbook(updated)

    return response


@router.get("/{playbook_id}/state")
async def get_playbook_state(playbook_id: int):
    """Get the current runtime state of a playbook."""
    engine = app_state.get("playbook_engine")
    if not engine:
        raise HTTPException(status_code=503, detail="Playbook engine not initialized")

    instance = engine.get_instance(playbook_id)
    if not instance:
        # Try loading from DB
        db: "Database" = app_state["db"]
        playbook = await db.get_playbook(playbook_id)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")

        state = None
        for symbol in playbook.config.symbols:
            state = await db.get_playbook_state(playbook_id, symbol)
        if state:
            return state.model_dump()
        return {"current_phase": "idle", "variables": {}, "bars_in_phase": 0}

    return instance.state.model_dump()


def _get_playbook_timeframes(config) -> list[str]:
    """Extract all unique timeframes from a playbook config."""
    tfs = set()
    for ind in config.indicators:
        tfs.add(ind.timeframe)
    for phase in config.phases.values():
        tfs.update(phase.evaluate_on)
    return list(tfs)
