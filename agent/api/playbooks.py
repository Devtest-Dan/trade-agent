"""Playbook API routes — build, manage, and refine execution playbooks."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.api.main import app_state

router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])


class BuildRequest(BaseModel):
    description: str


class RefineRequest(BaseModel):
    messages: list[dict]


class RefineFromBacktestRequest(BaseModel):
    backtest_id: int
    messages: list[dict]


class UpdateRequest(BaseModel):
    name: str | None = None
    description_nl: str | None = None
    explanation: str | None = None
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
    explanation = result.get("explanation", "")

    # Save playbook to DB
    from agent.models.playbook import Playbook

    playbook = Playbook(
        name=config.name,
        description_nl=req.description,
        explanation=explanation,
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
        "explanation": explanation,
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
            "explanation": p.explanation,
            "enabled": p.enabled,
            "autonomy": p.config.autonomy.value,
            "symbols": p.config.symbols,
            "phases": list(p.config.phases.keys()),
            "shadow_of": p.shadow_of,
            "is_shadow": p.is_shadow,
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
        "explanation": playbook.explanation,
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
    if req.explanation is not None:
        updates["explanation"] = req.explanation
    if req.config is not None:
        from agent.models.playbook import PlaybookConfig
        new_config = PlaybookConfig(**req.config)
        updates["config"] = new_config
        # Auto-version: save current config before overwriting
        await db.create_playbook_version(
            playbook_id,
            playbook.config.model_dump_json(by_alias=True),
            source="manual",
            notes="Before manual edit",
        )
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
    config_changed = False
    before_ver = None
    after_ver = None

    # If AI produced an updated config, save it
    if result["updated_config"]:
        # Version before overwriting
        before_ver = await db.create_playbook_version(
            playbook_id,
            playbook.config.model_dump_json(by_alias=True),
            source="refine",
            notes="Before journal-based refinement",
        )
        await db.update_playbook(playbook_id, config=result["updated_config"])
        config_changed = True
        response["updated"] = True
        response["config"] = result["updated_config"].model_dump(by_alias=True)

        # Reload in engine if enabled
        engine = app_state.get("playbook_engine")
        if engine and playbook.enabled:
            engine.unload_playbook(playbook_id)
            updated = await db.get_playbook(playbook_id)
            if updated:
                engine.load_playbook(updated)

    # Record refinement history
    import json as _json
    await db.create_refinement_record(
        playbook_id=playbook_id,
        source="journal",
        messages_json=_json.dumps(req.messages),
        reply=result["reply"],
        config_changed=config_changed,
        before_version=before_ver,
    )

    return response


@router.post("/{playbook_id}/refine-from-backtest")
async def refine_from_backtest(playbook_id: int, req: RefineFromBacktestRequest):
    """AI-assisted refinement using backtest results."""
    ai: "AIService" = app_state["ai_service"]
    db: "Database" = app_state["db"]

    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    # Load backtest run and trades
    run = await db.get_backtest_run(req.backtest_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    if run.get("playbook_id") != playbook_id:
        raise HTTPException(status_code=400, detail="Backtest run does not belong to this playbook")

    result_data = run.get("result", {})
    metrics = result_data.get("metrics", {})
    trades = result_data.get("trades", [])

    # If trades not in result blob, load from separate table
    if not trades:
        trades = await db.list_backtest_trades(req.backtest_id)

    result = await ai.refine_from_backtest(
        config=playbook.config.model_dump(by_alias=True),
        backtest_metrics=metrics,
        backtest_trades=trades,
        messages=req.messages,
    )

    response = {"reply": result["reply"]}
    config_changed = False
    before_ver = None

    # If AI produced an updated config, save it
    if result["updated_config"]:
        before_ver = await db.create_playbook_version(
            playbook_id,
            playbook.config.model_dump_json(by_alias=True),
            source="refine_backtest",
            notes=f"Before backtest-based refinement (backtest #{req.backtest_id})",
        )
        await db.update_playbook(playbook_id, config=result["updated_config"])
        config_changed = True
        response["updated"] = True
        response["config"] = result["updated_config"].model_dump(by_alias=True)

        # Reload in engine if enabled
        engine = app_state.get("playbook_engine")
        if engine and playbook.enabled:
            engine.unload_playbook(playbook_id)
            updated = await db.get_playbook(playbook_id)
            if updated:
                engine.load_playbook(updated)

    # Record refinement history
    import json as _json
    await db.create_refinement_record(
        playbook_id=playbook_id,
        source="backtest",
        messages_json=_json.dumps(req.messages),
        reply=result["reply"],
        config_changed=config_changed,
        before_version=before_ver,
        backtest_id=req.backtest_id,
    )

    return response


@router.get("/{playbook_id}/refinements")
async def list_refinements(playbook_id: int, limit: int = 20):
    """List refinement history for a playbook."""
    db: "Database" = app_state["db"]
    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    records = await db.list_refinement_history(playbook_id, limit=limit)
    return records


@router.get("/{playbook_id}/versions")
async def list_versions(playbook_id: int):
    """List all saved versions of a playbook's config."""
    db: "Database" = app_state["db"]
    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    versions = await db.list_playbook_versions(playbook_id)
    return {"current_config": playbook.config.model_dump(by_alias=True), "versions": versions}


@router.post("/{playbook_id}/rollback/{version}")
async def rollback_playbook(playbook_id: int, version: int):
    """Rollback a playbook to a previous version."""
    db: "Database" = app_state["db"]
    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    ver = await db.get_playbook_version(playbook_id, version)
    if not ver:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    import json
    from agent.models.playbook import PlaybookConfig

    # Save current config as a new version before rolling back
    await db.create_playbook_version(
        playbook_id,
        playbook.config.model_dump_json(by_alias=True),
        source="manual",
        notes=f"Before rollback to v{version}",
    )

    # Restore old config
    old_config = PlaybookConfig(**json.loads(ver["config_json"]))
    await db.update_playbook(playbook_id, config=old_config)

    # Reload in engine if enabled
    engine = app_state.get("playbook_engine")
    if engine and playbook.enabled:
        engine.unload_playbook(playbook_id)
        updated = await db.get_playbook(playbook_id)
        if updated:
            engine.load_playbook(updated)

    return {"status": "rolled_back", "to_version": version}


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


@router.post("/{playbook_id}/shadow")
async def create_shadow(playbook_id: int):
    """Create a shadow copy of a playbook for parallel paper-trading."""
    db: "Database" = app_state["db"]
    playbook = await db.get_playbook(playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    if playbook.is_shadow:
        raise HTTPException(status_code=400, detail="Cannot shadow a shadow playbook")

    # Check if a shadow already exists
    all_playbooks = await db.list_playbooks()
    existing = [p for p in all_playbooks if p.shadow_of == playbook_id]
    if existing:
        raise HTTPException(status_code=400, detail=f"Shadow already exists (id={existing[0].id}). Delete it first or promote it.")

    from agent.models.playbook import Playbook as PlaybookModel
    shadow = PlaybookModel(
        name=f"[Shadow] {playbook.name}",
        description_nl=playbook.description_nl,
        explanation=playbook.explanation,
        config=playbook.config,
        enabled=False,
        shadow_of=playbook_id,
        is_shadow=True,
    )
    shadow_id = await db.create_playbook(shadow)
    return {"id": shadow_id, "shadow_of": playbook_id, "name": shadow.name}


@router.post("/{playbook_id}/shadow/promote")
async def promote_shadow(playbook_id: int):
    """Promote a shadow playbook — replace the parent's config with the shadow's."""
    db: "Database" = app_state["db"]
    shadow = await db.get_playbook(playbook_id)
    if not shadow:
        raise HTTPException(status_code=404, detail="Playbook not found")
    if not shadow.is_shadow or not shadow.shadow_of:
        raise HTTPException(status_code=400, detail="This playbook is not a shadow")

    parent = await db.get_playbook(shadow.shadow_of)
    if not parent:
        raise HTTPException(status_code=404, detail="Parent playbook not found")

    # Version the parent before overwriting
    await db.create_playbook_version(
        parent.id,
        parent.config.model_dump_json(by_alias=True),
        source="shadow_promote",
        notes=f"Before promoting shadow #{playbook_id}",
    )

    # Copy shadow config to parent
    await db.update_playbook(parent.id, config=shadow.config)

    # Delete the shadow
    engine = app_state.get("playbook_engine")
    if engine:
        engine.unload_playbook(playbook_id)
    await db.delete_playbook(playbook_id)

    # Reload parent in engine if enabled
    if engine and parent.enabled:
        engine.unload_playbook(parent.id)
        updated = await db.get_playbook(parent.id)
        if updated:
            engine.load_playbook(updated)

    return {"status": "promoted", "parent_id": parent.id}


@router.get("/{playbook_id}/circuit-breaker")
async def get_circuit_breaker(playbook_id: int):
    """Get circuit breaker status for a playbook."""
    engine = app_state.get("playbook_engine")
    if not engine:
        raise HTTPException(status_code=503, detail="Playbook engine not available")

    instance = engine._instances.get(playbook_id)
    if not instance:
        return {
            "active": False,
            "consecutive_losses": 0,
            "error_count": 0,
            "tripped": False,
            "tripped_at": None,
            "config": {"max_consecutive_losses": 0, "max_errors": 0, "cooldown_minutes": 0},
        }

    state = instance.state
    cb_config = instance.config.risk.circuit_breaker
    is_active = engine.is_circuit_breaker_active(playbook_id)

    return {
        "active": is_active,
        "consecutive_losses": state.cb_consecutive_losses,
        "error_count": state.cb_error_count,
        "tripped": state.cb_tripped,
        "tripped_at": state.cb_tripped_at.isoformat() if state.cb_tripped_at else None,
        "config": {
            "max_consecutive_losses": cb_config.max_consecutive_losses,
            "max_errors": cb_config.max_errors,
            "cooldown_minutes": cb_config.cooldown_minutes,
        },
    }


@router.post("/{playbook_id}/circuit-breaker/reset")
async def reset_circuit_breaker(playbook_id: int):
    """Manually reset the circuit breaker for a playbook."""
    engine = app_state.get("playbook_engine")
    if not engine:
        raise HTTPException(status_code=503, detail="Playbook engine not available")

    ok = engine.reset_circuit_breaker(playbook_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Playbook not loaded in engine")

    return {"status": "reset", "playbook_id": playbook_id}


def _get_playbook_timeframes(config) -> list[str]:
    """Extract all unique timeframes from a playbook config."""
    tfs = set()
    for ind in config.indicators:
        tfs.add(ind.timeframe)
    for phase in config.phases.values():
        tfs.update(phase.evaluate_on)
    return list(tfs)
