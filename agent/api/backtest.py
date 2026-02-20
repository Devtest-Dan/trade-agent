"""Backtest API routes."""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from agent.api.main import app_state
from agent.backtest.bar_cache import fetch_and_cache, load_bars, get_cached_bar_count
from agent.backtest.engine import BacktestEngine
from agent.backtest.indicators import IndicatorEngine
from agent.backtest.models import BacktestConfig, BacktestRun

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


class StartBacktestRequest(BaseModel):
    playbook_id: int
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    bar_count: int = 500
    spread_pips: float = 0.3
    starting_balance: float = 10000.0


class FetchBarsRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    count: int = 500


@router.post("")
async def start_backtest(req: StartBacktestRequest):
    """Start a backtest run for a playbook."""
    db = app_state["db"]

    # Validate playbook exists
    playbook = await db.get_playbook(req.playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    config = BacktestConfig(
        playbook_id=req.playbook_id,
        symbol=req.symbol,
        timeframe=req.timeframe,
        bar_count=req.bar_count,
        spread_pips=req.spread_pips,
        starting_balance=req.starting_balance,
    )

    # Load bars from cache
    bars = await load_bars(db, req.symbol, req.timeframe, req.bar_count)

    # If not enough cached bars and MT5 is connected, fetch
    if len(bars) < req.bar_count and app_state.get("mt5_connected"):
        bridge = app_state["bridge"]
        bars = await fetch_and_cache(bridge, db, req.symbol, req.timeframe, req.bar_count)

    if len(bars) < 60:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough bars ({len(bars)} available, need at least 60). Use 'Fetch Bars' first.",
        )

    # Create run record
    run = BacktestRun(
        playbook_id=req.playbook_id,
        symbol=req.symbol,
        timeframe=req.timeframe,
        bar_count=len(bars),
        status="running",
        config=config,
    )
    run_id = await db.create_backtest_run(run)

    # Run backtest (synchronous computation in thread to not block)
    try:
        indicator_engine = IndicatorEngine(bars)
        engine = BacktestEngine(playbook.config, bars, indicator_engine, config)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, engine.run)

        # Store result
        await db.update_backtest_run(run_id, status="complete", result=result)

        # Store individual trades
        for trade in result.trades:
            await db.create_backtest_trade(run_id, trade)

        logger.info(f"Backtest #{run_id} complete: {result.metrics.total_trades} trades, PnL=${result.metrics.total_pnl}")

        return {
            "id": run_id,
            "status": "complete",
            "metrics": result.metrics.model_dump(),
            "trade_count": len(result.trades),
        }

    except Exception as e:
        logger.error(f"Backtest #{run_id} failed: {e}")
        await db.update_backtest_run(run_id, status="failed")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("")
async def list_backtests(playbook_id: int | None = None, limit: int = 50, offset: int = 0):
    """List backtest runs."""
    db = app_state["db"]
    runs = await db.list_backtest_runs(playbook_id=playbook_id, limit=limit, offset=offset)
    # Strip large result data from list view, keep metrics only
    for run in runs:
        if run.get("result"):
            run["result"] = {
                "metrics": run["result"].get("metrics"),
            }
    return runs


@router.get("/{run_id}")
async def get_backtest(run_id: int):
    """Get full backtest result including equity curve and trades."""
    db = app_state["db"]
    run = await db.get_backtest_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return run


@router.delete("/{run_id}")
async def delete_backtest(run_id: int):
    """Delete a backtest run and its trades."""
    db = app_state["db"]
    run = await db.get_backtest_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    await db.delete_backtest_run(run_id)
    return {"ok": True}


@router.post("/fetch-bars")
async def fetch_bars(req: FetchBarsRequest):
    """Fetch and cache bars from MT5."""
    if not app_state.get("mt5_connected"):
        raise HTTPException(status_code=503, detail="MT5 not connected")

    db = app_state["db"]
    bridge = app_state["bridge"]
    bars = await fetch_and_cache(bridge, db, req.symbol, req.timeframe, req.count)

    cached_count = await get_cached_bar_count(db, req.symbol, req.timeframe)

    return {
        "fetched": len(bars),
        "total_cached": cached_count,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
    }
