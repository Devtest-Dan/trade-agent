"""RSI Kernel Indicator — RSI with Nadaraya-Watson kernel regression overlay.

Computes standard RSI, then applies a Rational Quadratic kernel regression
to the RSI values for smoothing. The kernel line on RSI acts as a dynamic
overbought/oversold threshold — more adaptive than fixed 70/30 levels.

Based on PineScript "RSI with Kernel" by sammie123567858.
"""

import numpy as np
import pandas as pd
import pandas_ta as ta

from agent.backtest.ind_nw import rq_kernel_at, rq_kernel_series


# ─── Default outputs ──────────────────────────────────────────────────

RSI_KERNEL_EMPTY: dict[str, float] = {
    "rsi": 50.0,
    "kernel": 50.0,           # kernel regression on RSI
    "rsi_above_kernel": 0.0,  # 1.0 if RSI > kernel (bullish)
    "rsi_cross_above": 0.0,   # 1.0 if RSI just crossed above kernel
    "rsi_cross_below": 0.0,   # 1.0 if RSI just crossed below kernel
    "overbought": 0.0,        # 1.0 if RSI > ob level
    "oversold": 0.0,          # 1.0 if RSI < os level
    "kernel_rising": 0.0,     # 1.0 if kernel is rising
}


# ─── Computation ──────────────────────────────────────────────────────

def _compute_rsi_kernel(
    closes: np.ndarray,
    rsi_length: int = 14,
    kernel_lookback: int = 8,
    kernel_weight: float = 8.0,
    kernel_start: int = 25,
    kernel_smooth: bool = True,
    kernel_smooth_period: int = 4,
    ob_level: float = 70.0,
    os_level: float = 30.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute RSI and kernel regression on RSI.

    Returns (rsi_values, kernel_values) as numpy arrays of length n.
    """
    n = len(closes)
    rsi_vals = np.full(n, np.nan)
    kernel_vals = np.full(n, np.nan)

    if n < rsi_length + 1:
        return rsi_vals, kernel_vals

    # Compute RSI using pandas_ta
    series = pd.Series(closes)
    rsi_series = ta.rsi(series, length=rsi_length)
    if rsi_series is not None:
        for i in range(len(rsi_series)):
            if not pd.isna(rsi_series.iloc[i]):
                rsi_vals[i] = rsi_series.iloc[i]

    # Fill NaN RSI values with 50 for kernel computation
    rsi_for_kernel = np.where(np.isnan(rsi_vals), 50.0, rsi_vals)

    # Apply Rational Quadratic kernel regression to RSI
    kernel_raw = rq_kernel_series(rsi_for_kernel, kernel_lookback, kernel_weight, kernel_start)

    # Optional SMA smoothing on the kernel output
    if kernel_smooth and kernel_smooth_period > 1:
        smoothed = np.full(n, np.nan)
        for i in range(kernel_smooth_period - 1, n):
            smoothed[i] = np.mean(kernel_raw[i - kernel_smooth_period + 1:i + 1])
        kernel_vals = smoothed
    else:
        kernel_vals = kernel_raw

    return rsi_vals, kernel_vals


# ─── Point-in-time API ───────────────────────────────────────────────

def rsi_kernel_at(df: pd.DataFrame, params: dict) -> dict[str, float]:
    """Compute RSI Kernel at the last bar of df."""
    closes = df["close"].values
    n = len(closes)

    rsi_length = params.get("rsi_length", 14)
    kernel_lookback = params.get("kernel_lookback", 8)
    kernel_weight = params.get("kernel_weight", 8.0)
    kernel_start = params.get("kernel_start", 25)
    kernel_smooth = params.get("kernel_smooth", True)
    kernel_smooth_period = params.get("kernel_smooth_period", 4)
    ob_level = params.get("ob_level", 70.0)
    os_level = params.get("os_level", 30.0)

    if n < rsi_length + 2:
        return dict(RSI_KERNEL_EMPTY)

    rsi_vals, kernel_vals = _compute_rsi_kernel(
        closes, rsi_length, kernel_lookback, kernel_weight,
        kernel_start, kernel_smooth, kernel_smooth_period,
        ob_level, os_level,
    )

    rsi = rsi_vals[-1] if not np.isnan(rsi_vals[-1]) else 50.0
    kernel = kernel_vals[-1] if not np.isnan(kernel_vals[-1]) else 50.0
    prev_rsi = rsi_vals[-2] if n >= 2 and not np.isnan(rsi_vals[-2]) else rsi
    prev_kernel = kernel_vals[-2] if n >= 2 and not np.isnan(kernel_vals[-2]) else kernel

    return {
        "rsi": rsi,
        "kernel": kernel,
        "rsi_above_kernel": 1.0 if rsi > kernel else 0.0,
        "rsi_cross_above": 1.0 if rsi > kernel and prev_rsi <= prev_kernel else 0.0,
        "rsi_cross_below": 1.0 if rsi < kernel and prev_rsi >= prev_kernel else 0.0,
        "overbought": 1.0 if rsi > ob_level else 0.0,
        "oversold": 1.0 if rsi < os_level else 0.0,
        "kernel_rising": 1.0 if kernel > prev_kernel else 0.0,
    }


# ─── Full series API ─────────────────────────────────────────────────

def rsi_kernel_series(df: pd.DataFrame, params: dict) -> dict[str, list[float | None]]:
    """Compute RSI Kernel over all bars for charting."""
    closes = df["close"].values
    n = len(closes)

    rsi_length = params.get("rsi_length", 14)
    kernel_lookback = params.get("kernel_lookback", 8)
    kernel_weight = params.get("kernel_weight", 8.0)
    kernel_start = params.get("kernel_start", 25)
    kernel_smooth = params.get("kernel_smooth", True)
    kernel_smooth_period = params.get("kernel_smooth_period", 4)
    ob_level = params.get("ob_level", 70.0)
    os_level = params.get("os_level", 30.0)

    empty = {k: [None] * n for k in RSI_KERNEL_EMPTY}
    if n < rsi_length + 2:
        return empty

    rsi_vals, kernel_vals = _compute_rsi_kernel(
        closes, rsi_length, kernel_lookback, kernel_weight,
        kernel_start, kernel_smooth, kernel_smooth_period,
        ob_level, os_level,
    )

    result: dict[str, list[float | None]] = {k: [None] * n for k in RSI_KERNEL_EMPTY}

    for i in range(n):
        rsi = rsi_vals[i]
        kernel = kernel_vals[i]
        if np.isnan(rsi) or np.isnan(kernel):
            continue

        prev_rsi = rsi_vals[i - 1] if i > 0 and not np.isnan(rsi_vals[i - 1]) else rsi
        prev_kernel = kernel_vals[i - 1] if i > 0 and not np.isnan(kernel_vals[i - 1]) else kernel

        result["rsi"][i] = rsi
        result["kernel"][i] = kernel
        result["rsi_above_kernel"][i] = 1.0 if rsi > kernel else 0.0
        result["rsi_cross_above"][i] = 1.0 if rsi > kernel and prev_rsi <= prev_kernel else 0.0
        result["rsi_cross_below"][i] = 1.0 if rsi < kernel and prev_rsi >= prev_kernel else 0.0
        result["overbought"][i] = 1.0 if rsi > ob_level else 0.0
        result["oversold"][i] = 1.0 if rsi < os_level else 0.0
        result["kernel_rising"][i] = 1.0 if kernel > prev_kernel else 0.0

    return result
