"""Walk-forward validation and Monte Carlo simulation for strategy robustness testing."""

import asyncio
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from agent.backtest.engine import BacktestEngine
from agent.backtest.indicators import MultiTFIndicatorEngine
from agent.backtest.metrics import compute_metrics, compute_drawdown_curve
from agent.backtest.models import BacktestConfig, BacktestMetrics, BacktestTrade


# ── Monte Carlo ──────────────────────────────────────────────────────


@dataclass
class MonteCarloResult:
    """Results from Monte Carlo trade sequence simulation."""
    iterations: int
    original_pnl: float
    original_max_dd: float
    # Percentile results
    pnl_p5: float = 0.0
    pnl_p25: float = 0.0
    pnl_p50: float = 0.0
    pnl_p75: float = 0.0
    pnl_p95: float = 0.0
    dd_p5: float = 0.0
    dd_p25: float = 0.0
    dd_p50: float = 0.0
    dd_p75: float = 0.0
    dd_p95: float = 0.0
    # Probability of ruin (drawdown > X%)
    prob_ruin_20pct: float = 0.0
    prob_ruin_30pct: float = 0.0
    prob_ruin_50pct: float = 0.0
    # Distribution
    pnl_distribution: list[float] = field(default_factory=list)
    dd_distribution: list[float] = field(default_factory=list)


def run_monte_carlo(
    trades: list[BacktestTrade],
    starting_balance: float,
    iterations: int = 1000,
    seed: int | None = None,
) -> MonteCarloResult:
    """Shuffle trade sequence N times and compute P&L/DD distributions.

    This reveals how much of the result is due to the specific order
    of trades vs. the inherent edge of the strategy.
    """
    if not trades or iterations < 1:
        return MonteCarloResult(iterations=0, original_pnl=0, original_max_dd=0)

    if seed is not None:
        random.seed(seed)

    pnls = [t.pnl for t in trades]
    original_pnl = sum(pnls)

    # Original equity curve for max DD
    orig_equity = [starting_balance]
    for p in pnls:
        orig_equity.append(orig_equity[-1] + p)
    orig_dd_curve = compute_drawdown_curve(orig_equity)
    original_max_dd = abs(min(orig_dd_curve)) if orig_dd_curve else 0.0

    all_pnls = []
    all_dds = []
    ruin_20 = 0
    ruin_30 = 0
    ruin_50 = 0

    for _ in range(iterations):
        shuffled = pnls[:]
        random.shuffle(shuffled)

        # Build equity curve
        equity = starting_balance
        peak = equity
        max_dd_pct = 0.0
        total = 0.0

        for p in shuffled:
            equity += p
            total += p
            if equity > peak:
                peak = equity
            if peak > 0:
                dd_pct = (peak - equity) / peak * 100
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

        all_pnls.append(total)
        all_dds.append(max_dd_pct)

        if max_dd_pct > 20:
            ruin_20 += 1
        if max_dd_pct > 30:
            ruin_30 += 1
        if max_dd_pct > 50:
            ruin_50 += 1

    all_pnls.sort()
    all_dds.sort()

    def percentile(data: list[float], pct: float) -> float:
        idx = int(len(data) * pct / 100)
        idx = max(0, min(idx, len(data) - 1))
        return data[idx]

    return MonteCarloResult(
        iterations=iterations,
        original_pnl=round(original_pnl, 2),
        original_max_dd=round(original_max_dd, 2),
        pnl_p5=round(percentile(all_pnls, 5), 2),
        pnl_p25=round(percentile(all_pnls, 25), 2),
        pnl_p50=round(percentile(all_pnls, 50), 2),
        pnl_p75=round(percentile(all_pnls, 75), 2),
        pnl_p95=round(percentile(all_pnls, 95), 2),
        dd_p5=round(percentile(all_dds, 5), 2),
        dd_p25=round(percentile(all_dds, 25), 2),
        dd_p50=round(percentile(all_dds, 50), 2),
        dd_p75=round(percentile(all_dds, 75), 2),
        dd_p95=round(percentile(all_dds, 95), 2),
        prob_ruin_20pct=round(ruin_20 / iterations * 100, 1),
        prob_ruin_30pct=round(ruin_30 / iterations * 100, 1),
        prob_ruin_50pct=round(ruin_50 / iterations * 100, 1),
        pnl_distribution=all_pnls[::max(1, len(all_pnls) // 50)],  # 50 data points for chart
        dd_distribution=all_dds[::max(1, len(all_dds) // 50)],
    )


# ── Walk-Forward Validation ──────────────────────────────────────────


@dataclass
class WalkForwardWindow:
    """Result of a single in-sample / out-of-sample window."""
    window_idx: int
    in_sample_bars: int
    out_of_sample_bars: int
    in_sample_metrics: BacktestMetrics
    out_of_sample_metrics: BacktestMetrics
    in_sample_trades: int
    out_of_sample_trades: int


@dataclass
class WalkForwardResult:
    """Full walk-forward validation result."""
    total_windows: int
    total_bars: int
    in_sample_size: int
    out_of_sample_size: int
    step_size: int
    windows: list[WalkForwardWindow]
    # Aggregated out-of-sample performance
    oos_total_pnl: float = 0.0
    oos_avg_sharpe: float = 0.0
    oos_avg_win_rate: float = 0.0
    oos_total_trades: int = 0
    # Efficiency ratio: OOS performance / IS performance
    efficiency_ratio: float = 0.0
    duration_ms: int = 0


def _run_backtest_on_slice(
    playbook_config, bars_slice: list, multi_tf: MultiTFIndicatorEngine,
    bt_config: BacktestConfig, starting_balance: float
) -> tuple[BacktestMetrics, int]:
    """Run a backtest on a slice of bars. Returns (metrics, trade_count)."""
    from agent.backtest.models import BacktestConfig as BC
    config_copy = bt_config.model_copy()
    config_copy.starting_balance = starting_balance

    engine = BacktestEngine(playbook_config, bars_slice, multi_tf, config_copy)
    result = engine.run()
    return result.metrics, len(result.trades)


async def run_walk_forward(
    playbook_config,
    primary_bars: list,
    multi_tf: MultiTFIndicatorEngine,
    bt_config: BacktestConfig,
    in_sample_bars: int = 300,
    out_of_sample_bars: int = 100,
    step_bars: int = 100,
) -> WalkForwardResult:
    """Run walk-forward validation with rolling windows.

    Splits data into overlapping windows:
      [IS: 0..300][OOS: 300..400]
      [IS: 100..400][OOS: 400..500]
      [IS: 200..500][OOS: 500..600]
      ...

    Compares in-sample vs out-of-sample performance across windows.
    A strategy that works well in-sample but poorly OOS is overfit.
    """
    start = time.time()
    total_bars = len(primary_bars)
    min_needed = in_sample_bars + out_of_sample_bars

    if total_bars < min_needed:
        raise ValueError(
            f"Need at least {min_needed} bars for walk-forward "
            f"({in_sample_bars} IS + {out_of_sample_bars} OOS), got {total_bars}"
        )

    windows: list[WalkForwardWindow] = []
    offset = 0
    window_idx = 0

    loop = asyncio.get_event_loop()

    while offset + in_sample_bars + out_of_sample_bars <= total_bars:
        is_start = offset
        is_end = offset + in_sample_bars
        oos_start = is_end
        oos_end = oos_start + out_of_sample_bars

        is_bars = primary_bars[is_start:is_end]
        oos_bars = primary_bars[oos_start:oos_end]

        # Run both in thread pool
        is_metrics, is_trades = await loop.run_in_executor(
            None, _run_backtest_on_slice,
            playbook_config, is_bars, multi_tf, bt_config, bt_config.starting_balance,
        )
        oos_metrics, oos_trades = await loop.run_in_executor(
            None, _run_backtest_on_slice,
            playbook_config, oos_bars, multi_tf, bt_config, bt_config.starting_balance,
        )

        windows.append(WalkForwardWindow(
            window_idx=window_idx,
            in_sample_bars=len(is_bars),
            out_of_sample_bars=len(oos_bars),
            in_sample_metrics=is_metrics,
            out_of_sample_metrics=oos_metrics,
            in_sample_trades=is_trades,
            out_of_sample_trades=oos_trades,
        ))

        offset += step_bars
        window_idx += 1

    # Aggregate OOS metrics
    oos_pnl = sum(w.out_of_sample_metrics.total_pnl for w in windows)
    oos_sharpes = [w.out_of_sample_metrics.sharpe_ratio for w in windows if w.out_of_sample_trades > 0]
    oos_win_rates = [w.out_of_sample_metrics.win_rate for w in windows if w.out_of_sample_trades > 0]
    oos_trades = sum(w.out_of_sample_trades for w in windows)

    is_sharpes = [w.in_sample_metrics.sharpe_ratio for w in windows if w.in_sample_trades > 0]

    avg_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0
    avg_is_sharpe = sum(is_sharpes) / len(is_sharpes) if is_sharpes else 0
    efficiency = avg_oos_sharpe / avg_is_sharpe if avg_is_sharpe != 0 else 0

    duration = int((time.time() - start) * 1000)

    return WalkForwardResult(
        total_windows=len(windows),
        total_bars=total_bars,
        in_sample_size=in_sample_bars,
        out_of_sample_size=out_of_sample_bars,
        step_size=step_bars,
        windows=windows,
        oos_total_pnl=round(oos_pnl, 2),
        oos_avg_sharpe=round(avg_oos_sharpe, 2),
        oos_avg_win_rate=round(
            sum(oos_win_rates) / len(oos_win_rates) if oos_win_rates else 0, 1
        ),
        oos_total_trades=oos_trades,
        efficiency_ratio=round(efficiency, 2),
        duration_ms=duration,
    )
