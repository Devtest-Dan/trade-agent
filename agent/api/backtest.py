"""Backtest API routes."""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from agent.api.main import app_state
from agent.backtest.bar_cache import fetch_and_cache, load_bars, load_bars_by_date, get_cached_bar_count
from agent.backtest.engine import BacktestEngine
from agent.backtest.indicators import MultiTFIndicatorEngine, _tf_to_minutes
from agent.backtest.models import BacktestConfig, BacktestRun
from agent.backtest.hypotheses import generate_hypotheses, Hypothesis
from agent.backtest.sweep import SweepParam, run_sweep
from agent.backtest.validation import run_monte_carlo, run_walk_forward, MonteCarloResult

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


class StartBacktestRequest(BaseModel):
    playbook_id: int
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    bar_count: int = 500
    spread_pips: float = 0.3
    slippage_pips: float = 0.0
    commission_per_lot: float = 0.0
    starting_balance: float = 10000.0
    start_date: str | None = None
    end_date: str | None = None


class FetchBarsRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    count: int = 500


class MonteCarloRequest(BaseModel):
    backtest_id: int
    iterations: int = 1000


class WalkForwardRequest(BaseModel):
    playbook_id: int
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    bar_count: int = 1000
    spread_pips: float = 0.3
    slippage_pips: float = 0.0
    commission_per_lot: float = 0.0
    starting_balance: float = 10000.0
    in_sample_bars: int = 300
    out_of_sample_bars: int = 100
    step_bars: int = 100


class SweepParamInput(BaseModel):
    path: str  # "variables.rsi_threshold", "risk.max_lot", "spread_pips"
    values: list[float]


class StartSweepRequest(BaseModel):
    playbook_id: int
    symbol: str = "XAUUSD"
    timeframe: str = "H4"
    bar_count: int = 500
    spread_pips: float = 0.3
    slippage_pips: float = 0.0
    commission_per_lot: float = 0.0
    starting_balance: float = 10000.0
    params: list[SweepParamInput]
    rank_by: str = "sharpe_ratio"  # sharpe_ratio, total_pnl, profit_factor


async def _load_multi_tf_bars(
    db, playbook_config, primary_tf: str, bar_count: int, symbol: str,
    start_date: str | None = None, end_date: str | None = None,
):
    """Load bars for all TFs referenced in playbook indicators.

    If start_date/end_date are provided, loads bars within that range.
    Otherwise uses bar_count (last N bars).
    For non-primary timeframes, calculates the equivalent bar count
    based on the total time span of the primary bars, with a 20% buffer.
    """
    primary_min = _tf_to_minutes(primary_tf)
    total_minutes = bar_count * primary_min

    # Collect all unique timeframes (primary + any indicator TFs)
    tfs = {primary_tf.upper()}
    for ind in playbook_config.indicators:
        if ind.timeframe:
            tfs.add(ind.timeframe.upper())

    bridge = app_state.get("bridge") if app_state.get("mt5_connected") else None
    use_dates = bool(start_date or end_date)

    tf_bars: dict[str, list] = {}
    for tf in tfs:
        if use_dates:
            bars = await load_bars_by_date(db, symbol, tf, start_date, end_date)
        else:
            if tf == primary_tf.upper():
                needed = bar_count
            else:
                needed = int((total_minutes / _tf_to_minutes(tf)) * 1.2) + 50
            needed = max(needed, 60)

            bars = await load_bars(db, symbol, tf, needed)
            if len(bars) < needed and bridge:
                bars = await fetch_and_cache(bridge, db, symbol, tf, needed)
        tf_bars[tf] = bars

    return tf_bars


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
        slippage_pips=req.slippage_pips,
        commission_per_lot=req.commission_per_lot,
        starting_balance=req.starting_balance,
        start_date=req.start_date,
        end_date=req.end_date,
    )

    # Load bars for all required timeframes
    tf_bars = await _load_multi_tf_bars(
        db, playbook.config, req.timeframe, req.bar_count, req.symbol,
        start_date=req.start_date, end_date=req.end_date,
    )
    primary_bars = tf_bars.get(req.timeframe.upper(), [])

    if len(primary_bars) < 60:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough bars ({len(primary_bars)} available, need at least 60). Use 'Fetch Bars' first.",
        )

    # Create run record
    run = BacktestRun(
        playbook_id=req.playbook_id,
        symbol=req.symbol,
        timeframe=req.timeframe,
        bar_count=len(primary_bars),
        status="running",
        config=config,
    )
    run_id = await db.create_backtest_run(run)

    # Run backtest (synchronous computation in thread to not block)
    try:
        multi = MultiTFIndicatorEngine()
        for tf, bars in tf_bars.items():
            multi.add_timeframe(tf, bars)

        engine = BacktestEngine(playbook.config, primary_bars, multi, config)

        loop = asyncio.get_event_loop()

        def _run_all():
            multi.precompute(playbook.config.indicators)
            return engine.run()

        result = await loop.run_in_executor(None, _run_all)

        # Store result
        await db.update_backtest_run(run_id, status="complete", result=result)

        # Batch trade writes (single commit instead of N commits)
        if result.trades:
            await db.create_backtest_trades_batch(run_id, result.trades)

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


@router.post("/{run_id}/monte-carlo")
async def monte_carlo(run_id: int, req: MonteCarloRequest):
    """Run Monte Carlo simulation on a completed backtest's trades."""
    db = app_state["db"]

    run = await db.get_backtest_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")

    result_data = run.get("result", {})
    raw_trades = result_data.get("trades", [])
    if not raw_trades:
        raw_trades = await db.list_backtest_trades(run_id)

    if len(raw_trades) < 5:
        raise HTTPException(status_code=400, detail=f"Need at least 5 trades for Monte Carlo, got {len(raw_trades)}")

    # Convert to BacktestTrade objects
    from agent.backtest.models import BacktestTrade
    trades = [BacktestTrade(**t) if isinstance(t, dict) else t for t in raw_trades]

    config = result_data.get("config", {})
    starting_balance = config.get("starting_balance", 10000.0)

    iterations = min(req.iterations, 5000)  # cap at 5000
    loop = asyncio.get_event_loop()
    mc = await loop.run_in_executor(
        None, run_monte_carlo, trades, starting_balance, iterations
    )

    return {
        "iterations": mc.iterations,
        "original_pnl": mc.original_pnl,
        "original_max_dd": mc.original_max_dd,
        "pnl_percentiles": {
            "p5": mc.pnl_p5, "p25": mc.pnl_p25, "p50": mc.pnl_p50,
            "p75": mc.pnl_p75, "p95": mc.pnl_p95,
        },
        "drawdown_percentiles": {
            "p5": mc.dd_p5, "p25": mc.dd_p25, "p50": mc.dd_p50,
            "p75": mc.dd_p75, "p95": mc.dd_p95,
        },
        "probability_of_ruin": {
            "20pct": mc.prob_ruin_20pct,
            "30pct": mc.prob_ruin_30pct,
            "50pct": mc.prob_ruin_50pct,
        },
        "pnl_distribution": mc.pnl_distribution,
        "dd_distribution": mc.dd_distribution,
    }


@router.post("/walk-forward")
async def walk_forward(req: WalkForwardRequest):
    """Run walk-forward validation to test strategy robustness."""
    db = app_state["db"]

    playbook = await db.get_playbook(req.playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    bt_config = BacktestConfig(
        playbook_id=req.playbook_id,
        symbol=req.symbol,
        timeframe=req.timeframe,
        bar_count=req.bar_count,
        spread_pips=req.spread_pips,
        slippage_pips=req.slippage_pips,
        commission_per_lot=req.commission_per_lot,
        starting_balance=req.starting_balance,
    )

    tf_bars = await _load_multi_tf_bars(db, playbook.config, req.timeframe, req.bar_count, req.symbol)
    primary_bars = tf_bars.get(req.timeframe.upper(), [])

    min_needed = req.in_sample_bars + req.out_of_sample_bars
    if len(primary_bars) < min_needed:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {min_needed} bars, got {len(primary_bars)}",
        )

    # Precompute indicators
    multi = MultiTFIndicatorEngine()
    for tf, bars in tf_bars.items():
        multi.add_timeframe(tf, bars)
    multi.precompute(playbook.config.indicators)

    wf = await run_walk_forward(
        playbook.config, primary_bars, multi, bt_config,
        req.in_sample_bars, req.out_of_sample_bars, req.step_bars,
    )

    return {
        "total_windows": wf.total_windows,
        "total_bars": wf.total_bars,
        "in_sample_size": wf.in_sample_size,
        "out_of_sample_size": wf.out_of_sample_size,
        "step_size": wf.step_size,
        "oos_total_pnl": wf.oos_total_pnl,
        "oos_avg_sharpe": wf.oos_avg_sharpe,
        "oos_avg_win_rate": wf.oos_avg_win_rate,
        "oos_total_trades": wf.oos_total_trades,
        "efficiency_ratio": wf.efficiency_ratio,
        "duration_ms": wf.duration_ms,
        "windows": [
            {
                "window": w.window_idx,
                "in_sample": {
                    "bars": w.in_sample_bars,
                    "trades": w.in_sample_trades,
                    "pnl": w.in_sample_metrics.total_pnl,
                    "sharpe": w.in_sample_metrics.sharpe_ratio,
                    "win_rate": w.in_sample_metrics.win_rate,
                },
                "out_of_sample": {
                    "bars": w.out_of_sample_bars,
                    "trades": w.out_of_sample_trades,
                    "pnl": w.out_of_sample_metrics.total_pnl,
                    "sharpe": w.out_of_sample_metrics.sharpe_ratio,
                    "win_rate": w.out_of_sample_metrics.win_rate,
                },
            }
            for w in wf.windows
        ],
    }


@router.post("/sweep")
async def start_sweep(req: StartSweepRequest):
    """Run a parameter sweep — backtests across all parameter combinations."""
    db = app_state["db"]

    playbook = await db.get_playbook(req.playbook_id)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    if not req.params:
        raise HTTPException(status_code=400, detail="No sweep parameters provided")

    # Validate combination count (cap at 500 to prevent abuse)
    total = 1
    for p in req.params:
        if len(p.values) < 2:
            raise HTTPException(status_code=400, detail=f"Parameter '{p.path}' needs at least 2 values")
        total *= len(p.values)
    if total > 500:
        raise HTTPException(status_code=400, detail=f"Too many combinations ({total}). Max 500.")

    bt_config = BacktestConfig(
        playbook_id=req.playbook_id,
        symbol=req.symbol,
        timeframe=req.timeframe,
        bar_count=req.bar_count,
        spread_pips=req.spread_pips,
        slippage_pips=req.slippage_pips,
        commission_per_lot=req.commission_per_lot,
        starting_balance=req.starting_balance,
    )

    # Load bars
    tf_bars = await _load_multi_tf_bars(db, playbook.config, req.timeframe, req.bar_count, req.symbol)
    primary_bars = tf_bars.get(req.timeframe.upper(), [])
    if len(primary_bars) < 60:
        raise HTTPException(status_code=400, detail=f"Not enough bars ({len(primary_bars)}). Need at least 60.")

    # Precompute indicators once (shared across all runs)
    multi = MultiTFIndicatorEngine()
    for tf, bars in tf_bars.items():
        multi.add_timeframe(tf, bars)
    multi.precompute(playbook.config.indicators)

    sweep_params = [SweepParam(path=p.path, values=p.values) for p in req.params]
    pb_dict = playbook.config.model_dump(by_alias=True)

    result = await run_sweep(pb_dict, primary_bars, multi, bt_config, sweep_params)

    # Format response
    rank_key = req.rank_by
    runs_sorted = sorted(
        result.runs,
        key=lambda r: getattr(r.metrics, rank_key, 0),
        reverse=True,
    )

    return {
        "total_combinations": result.total_combinations,
        "completed": result.completed,
        "failed": result.failed,
        "duration_ms": result.duration_ms,
        "rank_by": rank_key,
        "runs": [
            {
                "rank": i + 1,
                "params": r.params,
                "metrics": r.metrics.model_dump(),
                "trade_count": r.trade_count,
            }
            for i, r in enumerate(runs_sorted)
        ],
        "best": {
            "by_sharpe": result.best_by_sharpe.params if result.best_by_sharpe else None,
            "by_pnl": result.best_by_pnl.params if result.best_by_pnl else None,
            "by_profit_factor": result.best_by_profit_factor.params if result.best_by_profit_factor else None,
        },
    }


@router.get("/{run_id}/hypotheses")
async def get_hypotheses(run_id: int):
    """Auto-generate improvement hypotheses from backtest results."""
    db = app_state["db"]

    run = await db.get_backtest_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")

    result_data = run.get("result", {})
    raw_trades = result_data.get("trades", [])
    if not raw_trades:
        raw_trades = await db.list_backtest_trades(run_id)

    raw_metrics = result_data.get("metrics", {})

    from agent.backtest.models import BacktestTrade, BacktestMetrics
    trades = [BacktestTrade(**t) if isinstance(t, dict) else t for t in raw_trades]
    metrics = BacktestMetrics(**raw_metrics) if isinstance(raw_metrics, dict) else raw_metrics

    hypotheses = generate_hypotheses(trades, metrics)

    return {
        "run_id": run_id,
        "count": len(hypotheses),
        "hypotheses": [
            {
                "category": h.category,
                "observation": h.observation,
                "suggestion": h.suggestion,
                "confidence": h.confidence,
                "param_path": h.param_path,
                "current_value": h.current_value,
                "suggested_value": h.suggested_value,
            }
            for h in hypotheses
        ],
    }


@router.get("/compare")
async def compare_backtests(ids: str):
    """Compare multiple backtest runs side-by-side.

    ids: comma-separated run IDs (e.g., ?ids=1,2,3)
    """
    db = app_state["db"]

    run_ids = [int(x.strip()) for x in ids.split(",") if x.strip().isdigit()]
    if len(run_ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 run IDs to compare")
    if len(run_ids) > 10:
        raise HTTPException(status_code=400, detail="Max 10 runs for comparison")

    runs = []
    for rid in run_ids:
        run = await db.get_backtest_run(rid)
        if run:
            result = run.get("result", {})
            runs.append({
                "id": run.get("id", rid),
                "playbook_id": run.get("playbook_id"),
                "symbol": run.get("symbol"),
                "timeframe": run.get("timeframe"),
                "bar_count": run.get("bar_count"),
                "status": run.get("status"),
                "metrics": result.get("metrics", {}),
                "equity_curve": result.get("equity_curve", []),
                "trade_count": len(result.get("trades", [])),
                "created_at": run.get("created_at"),
            })

    if len(runs) < 2:
        raise HTTPException(status_code=400, detail="Could not find enough valid runs")

    # Compute deltas between first (baseline) and each other run
    baseline = runs[0]["metrics"]
    for run in runs[1:]:
        m = run["metrics"]
        run["delta"] = {
            "total_pnl": round(m.get("total_pnl", 0) - baseline.get("total_pnl", 0), 2),
            "win_rate": round(m.get("win_rate", 0) - baseline.get("win_rate", 0), 1),
            "sharpe_ratio": round(m.get("sharpe_ratio", 0) - baseline.get("sharpe_ratio", 0), 2),
            "profit_factor": round(m.get("profit_factor", 0) - baseline.get("profit_factor", 0), 2),
            "max_drawdown_pct": round(m.get("max_drawdown_pct", 0) - baseline.get("max_drawdown_pct", 0), 1),
        }

    return {"baseline_id": run_ids[0], "runs": runs}


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
