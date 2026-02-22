"""Parameter sweep engine — run backtests across parameter combinations."""

import asyncio
import copy
import itertools
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from agent.backtest.engine import BacktestEngine
from agent.backtest.indicators import MultiTFIndicatorEngine
from agent.backtest.models import BacktestConfig, BacktestMetrics, BacktestResult


@dataclass
class SweepParam:
    """A parameter to sweep."""
    path: str  # "variables.rsi_threshold", "risk.max_lot", "spread_pips"
    values: list[float]


@dataclass
class SweepRunResult:
    """Result of a single sweep run."""
    params: dict[str, float]
    metrics: BacktestMetrics
    trade_count: int
    equity_curve: list[float] = field(default_factory=list)


@dataclass
class SweepResult:
    """Full sweep result."""
    total_combinations: int
    completed: int
    failed: int
    duration_ms: int
    runs: list[SweepRunResult]
    best_by_sharpe: SweepRunResult | None = None
    best_by_pnl: SweepRunResult | None = None
    best_by_profit_factor: SweepRunResult | None = None


def _apply_params(
    playbook_config: dict, backtest_config: BacktestConfig, params: dict[str, float]
) -> tuple[dict, BacktestConfig]:
    """Apply parameter overrides to playbook and backtest configs.

    Supported paths:
        variables.<name>     → playbook variable default
        risk.<field>         → playbook risk config field
        spread_pips          → backtest spread
        starting_balance     → backtest starting balance
    """
    pb = copy.deepcopy(playbook_config)
    bt = backtest_config.model_copy()

    for path, value in params.items():
        parts = path.split(".")
        if parts[0] == "variables" and len(parts) == 2:
            var_name = parts[1]
            if var_name in pb.get("variables", {}):
                pb["variables"][var_name]["default"] = value
            else:
                logger.warning(f"Sweep: variable '{var_name}' not found in playbook")
        elif parts[0] == "risk" and len(parts) == 2:
            field_name = parts[1]
            if "risk" in pb and field_name in pb["risk"]:
                pb["risk"][field_name] = value
            else:
                logger.warning(f"Sweep: risk field '{field_name}' not found")
        elif path == "spread_pips":
            bt.spread_pips = value
        elif path == "starting_balance":
            bt.starting_balance = value
        else:
            logger.warning(f"Sweep: unknown parameter path '{path}'")

    return pb, bt


def _run_single(
    playbook_config_dict: dict,
    primary_bars: list,
    multi_tf: MultiTFIndicatorEngine,
    bt_config: BacktestConfig,
    params: dict[str, float],
) -> SweepRunResult | None:
    """Run a single backtest with parameter overrides. Thread-safe."""
    try:
        from agent.models.playbook import PlaybookConfig

        modified_pb, modified_bt = _apply_params(playbook_config_dict, bt_config, params)
        config = PlaybookConfig(**modified_pb)

        engine = BacktestEngine(config, primary_bars, multi_tf, modified_bt)
        result = engine.run()

        return SweepRunResult(
            params=params,
            metrics=result.metrics,
            trade_count=len(result.trades),
            equity_curve=result.equity_curve,
        )
    except Exception as e:
        logger.error(f"Sweep run failed for params {params}: {e}")
        return None


async def run_sweep(
    playbook_config_dict: dict,
    primary_bars: list,
    multi_tf: MultiTFIndicatorEngine,
    bt_config: BacktestConfig,
    sweep_params: list[SweepParam],
    max_workers: int = 4,
) -> SweepResult:
    """Run parameter sweep across all combinations.

    Precomputes indicators once, then runs backtests in parallel.
    """
    start = time.time()

    # Generate cartesian product of all parameter values
    param_names = [p.path for p in sweep_params]
    param_values = [p.values for p in sweep_params]
    combinations = [
        dict(zip(param_names, combo))
        for combo in itertools.product(*param_values)
    ]
    total = len(combinations)
    logger.info(f"Sweep: {total} combinations across {len(sweep_params)} parameters")

    # Run backtests in thread pool
    loop = asyncio.get_event_loop()
    runs: list[SweepRunResult] = []
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []
        for combo in combinations:
            f = loop.run_in_executor(
                pool,
                _run_single,
                playbook_config_dict,
                primary_bars,
                multi_tf,
                bt_config,
                combo,
            )
            futures.append(f)

        results = await asyncio.gather(*futures)

    for r in results:
        if r is not None:
            runs.append(r)
        else:
            failed += 1

    # Rank by different metrics
    best_sharpe = max(runs, key=lambda r: r.metrics.sharpe_ratio) if runs else None
    best_pnl = max(runs, key=lambda r: r.metrics.total_pnl) if runs else None
    best_pf = max(runs, key=lambda r: r.metrics.profit_factor) if runs else None

    duration = int((time.time() - start) * 1000)
    logger.info(f"Sweep complete: {len(runs)}/{total} succeeded in {duration}ms")

    return SweepResult(
        total_combinations=total,
        completed=len(runs),
        failed=failed,
        duration_ms=duration,
        runs=sorted(runs, key=lambda r: r.metrics.sharpe_ratio, reverse=True),
        best_by_sharpe=best_sharpe,
        best_by_pnl=best_pnl,
        best_by_profit_factor=best_pf,
    )
