"""Knowledge / Skill Graph API routes."""

from fastapi import APIRouter, HTTPException

from agent.api.main import app_state
from agent.models.knowledge import (
    SkillNodeCreate, SkillEdgeCreate, SkillNode, SkillEdge,
    SkillCategory, Confidence, EdgeRelationship,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/skills")
async def list_skills(
    category: str | None = None,
    confidence: str | None = None,
    symbol: str | None = None,
    playbook_id: int | None = None,
    market_regime: str | None = None,
    source_type: str | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    """List/search skill nodes with filters."""
    db = app_state["db"]
    nodes = await db.list_skill_nodes(
        category=category,
        confidence=confidence,
        symbol=symbol,
        playbook_id=playbook_id,
        market_regime=market_regime,
        source_type=source_type,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [n.model_dump(mode="json") for n in nodes]


@router.post("/skills")
async def create_skill(req: SkillNodeCreate):
    """Create a manual skill node."""
    db = app_state["db"]
    node = SkillNode(
        category=req.category,
        title=req.title,
        description=req.description,
        confidence=req.confidence,
        source_type="manual",
        symbol=req.symbol,
        timeframe=req.timeframe,
        market_regime=req.market_regime,
        sample_size=req.sample_size,
        win_rate=req.win_rate,
        avg_pnl=req.avg_pnl,
        avg_rr=req.avg_rr,
        indicators_json=req.indicators_json,
        tags=req.tags,
    )
    node_id = await db.create_skill_node(node)
    node.id = node_id
    return node.model_dump(mode="json")


@router.get("/skills/{node_id}")
async def get_skill(node_id: int):
    """Get a skill node with its edges."""
    db = app_state["db"]
    node = await db.get_skill_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Skill node not found")
    edges = await db.list_skill_edges(node_id)
    result = node.model_dump(mode="json")
    result["edges"] = [e.model_dump(mode="json") for e in edges]
    return result


@router.put("/skills/{node_id}")
async def update_skill(node_id: int, req: SkillNodeCreate):
    """Update a skill node."""
    db = app_state["db"]
    existing = await db.get_skill_node(node_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Skill node not found")
    await db.update_skill_node(
        node_id,
        category=req.category,
        title=req.title,
        description=req.description,
        confidence=req.confidence,
        symbol=req.symbol,
        timeframe=req.timeframe,
        market_regime=req.market_regime,
        sample_size=req.sample_size,
        win_rate=req.win_rate,
        avg_pnl=req.avg_pnl,
        avg_rr=req.avg_rr,
        indicators_json=req.indicators_json,
        tags=req.tags,
    )
    updated = await db.get_skill_node(node_id)
    return updated.model_dump(mode="json")


@router.delete("/skills/{node_id}")
async def delete_skill(node_id: int):
    """Delete a skill node and its edges."""
    db = app_state["db"]
    deleted = await db.delete_skill_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill node not found")
    return {"deleted": True}


@router.get("/skills/{node_id}/graph")
async def get_skill_graph(node_id: int, depth: int = 2):
    """BFS graph traversal from a skill node."""
    db = app_state["db"]
    node = await db.get_skill_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Skill node not found")
    graph = await db.get_skill_graph(node_id, depth=min(depth, 5))
    return {
        "nodes": [n.model_dump(mode="json") for n in graph["nodes"]],
        "edges": [e.model_dump(mode="json") for e in graph["edges"]],
    }


@router.post("/extract/{backtest_id}")
async def extract_from_backtest(backtest_id: int):
    """Extract skill nodes from a backtest run."""
    db = app_state["db"]
    run = await db.get_backtest_run(backtest_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")

    playbook_id = run.get("playbook_id")
    symbol = run.get("symbol", "")
    timeframe = run.get("timeframe", "")

    result_data = run.get("result", {})
    trades = result_data.get("trades", [])
    metrics = result_data.get("metrics", {})

    if not trades:
        trades = await db.list_backtest_trades(backtest_id)

    if not trades:
        raise HTTPException(status_code=400, detail="No trades found in backtest")

    from agent.knowledge_extractor import extract_skills_from_backtest
    result = await extract_skills_from_backtest(
        db=db,
        run_id=backtest_id,
        playbook_id=playbook_id,
        symbol=symbol,
        timeframe=timeframe,
        trades=trades,
        metrics=metrics,
    )
    return result


@router.delete("/extract/{backtest_id}")
async def delete_extracted_skills(backtest_id: int):
    """Delete all skill nodes extracted from a backtest."""
    db = app_state["db"]
    deleted = await db.delete_skills_for_backtest(backtest_id)
    return {"deleted": deleted}


@router.post("/edges")
async def create_edge(req: SkillEdgeCreate):
    """Create an edge between two skill nodes."""
    db = app_state["db"]
    # Verify both nodes exist
    src = await db.get_skill_node(req.source_id)
    tgt = await db.get_skill_node(req.target_id)
    if not src or not tgt:
        raise HTTPException(status_code=404, detail="Source or target node not found")
    edge = SkillEdge(
        source_id=req.source_id,
        target_id=req.target_id,
        relationship=req.relationship,
        weight=req.weight,
        reason=req.reason,
    )
    edge_id = await db.create_skill_edge(edge)
    edge.id = edge_id
    return edge.model_dump(mode="json")


@router.delete("/edges/{edge_id}")
async def delete_edge(edge_id: int):
    """Delete an edge."""
    db = app_state["db"]
    deleted = await db.delete_skill_edge(edge_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"deleted": True}


@router.get("/graph")
async def full_graph():
    """Return all nodes and edges for graph visualization."""
    db = app_state["db"]
    nodes = await db.list_skill_nodes(limit=500)
    edges = await db.list_skill_edges()
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "edges": [e.model_dump(mode="json") for e in edges],
    }


@router.get("/stats")
async def knowledge_stats():
    """Summary stats for the skill graph."""
    db = app_state["db"]
    total = await db.count_skill_nodes()
    high = await db.count_skill_nodes(confidence="HIGH")
    medium = await db.count_skill_nodes(confidence="MEDIUM")
    low = await db.count_skill_nodes(confidence="LOW")

    # Category breakdown
    categories = {}
    for cat in SkillCategory:
        categories[cat.value] = await db.count_skill_nodes(category=cat.value)

    return {
        "total": total,
        "by_confidence": {"HIGH": high, "MEDIUM": medium, "LOW": low},
        "by_category": categories,
    }
