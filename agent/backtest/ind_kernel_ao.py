"""Kernel AO (Awesome Oscillator) — PineScript conversion.

Dual-kernel oscillator: fast RQ kernel minus slow RQ kernel on close prices,
with optional SMA smoothing. Then applies RQ kernels on the oscillator itself
to derive smoothed signal lines.

Based on PineScript Kernel AO Oscillator.
"""

from typing import Any

import numpy as np
import pandas as pd

from agent.backtest.ind_nw import rq_kernel_at, rq_kernel_series


# ─── Empty output template ────────────────────────────────────────────

KERNEL_AO_EMPTY: dict[str, float] = {
    "osc": 0.0,
    "diff": 0.0,
    "is_rising": 0.0,
    "kernel_fast": 0.0,
    "kernel_slow": 0.0,
    "fast_rising": 0.0,
    "slow_rising": 0.0,
}


# ─── Helpers ──────────────────────────────────────────────────────────

def _sma_smooth(values: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average smoothing. NaN-safe: propagates NaN for early bars."""
    if period <= 1:
        return values.copy()
    n = len(values)
    result = np.full(n, np.nan)
    cumsum = 0.0
    count = 0
    for i in range(n):
        if np.isnan(values[i]):
            continue
        cumsum += values[i]
        count += 1
        if count >= period:
            # Compute mean of last `period` values
            window_sum = 0.0
            valid = 0
            for j in range(period):
                idx = i - j
                if idx >= 0 and not np.isnan(values[idx]):
                    window_sum += values[idx]
                    valid += 1
            if valid == period:
                result[i] = window_sum / period
    return result


def _extract_params(params: dict[str, Any]) -> tuple:
    """Extract and return all Kernel AO parameters with defaults."""
    fast_lookback = params.get("fast_lookback", 5)
    fast_weight = params.get("fast_weight", 8.0)
    fast_start = params.get("fast_start", 25)
    fast_smooth = params.get("fast_smooth", True)
    fast_smooth_period = params.get("fast_smooth_period", 4)

    slow_lookback = params.get("slow_lookback", 34)
    slow_weight = params.get("slow_weight", 3.0)
    slow_start = params.get("slow_start", 120)
    slow_smooth = params.get("slow_smooth", True)
    slow_smooth_period = params.get("slow_smooth_period", 40)

    # Params for kernels applied ON the oscillator
    osc_fast_lookback = params.get("osc_fast_lookback", fast_lookback)
    osc_fast_weight = params.get("osc_fast_weight", fast_weight)
    osc_fast_start = params.get("osc_fast_start", fast_start)

    osc_slow_lookback = params.get("osc_slow_lookback", slow_lookback)
    osc_slow_weight = params.get("osc_slow_weight", slow_weight)
    osc_slow_start = params.get("osc_slow_start", slow_start)

    return (
        fast_lookback, fast_weight, fast_start, fast_smooth, fast_smooth_period,
        slow_lookback, slow_weight, slow_start, slow_smooth, slow_smooth_period,
        osc_fast_lookback, osc_fast_weight, osc_fast_start,
        osc_slow_lookback, osc_slow_weight, osc_slow_start,
    )


# ─── Point-in-time (last bar) ────────────────────────────────────────

def kernel_ao_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute Kernel AO at the last bar of df (no look-ahead).

    Args:
        df: DataFrame with 'close' column, sliced up to current bar.
        params: See _extract_params for keys and defaults.

    Returns:
        dict matching KERNEL_AO_EMPTY keys.
    """
    (
        fast_lookback, fast_weight, fast_start, fast_smooth, fast_smooth_period,
        slow_lookback, slow_weight, slow_start, slow_smooth, slow_smooth_period,
        osc_fast_lookback, osc_fast_weight, osc_fast_start,
        osc_slow_lookback, osc_slow_weight, osc_slow_start,
    ) = _extract_params(params)

    closes = df["close"].values
    n = len(df)

    if n < 3:
        return dict(KERNEL_AO_EMPTY)

    # Step 1-2: Compute fast and slow kernel series on close, optionally smoothed
    fast_raw = rq_kernel_series(closes, float(fast_lookback), fast_weight, fast_start)
    if fast_smooth:
        fast_k = _sma_smooth(fast_raw, fast_smooth_period)
    else:
        fast_k = fast_raw

    slow_raw = rq_kernel_series(closes, float(slow_lookback), slow_weight, slow_start)
    if slow_smooth:
        slow_k = _sma_smooth(slow_raw, slow_smooth_period)
    else:
        slow_k = slow_raw

    # Step 3: Oscillator = fast - slow
    osc_arr = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(fast_k[i]) and not np.isnan(slow_k[i]):
            osc_arr[i] = fast_k[i] - slow_k[i]

    bar = n - 1
    osc_val = float(osc_arr[bar]) if not np.isnan(osc_arr[bar]) else 0.0

    # Step 4: diff = osc[i] - osc[i-1]
    osc_prev = float(osc_arr[bar - 1]) if bar >= 1 and not np.isnan(osc_arr[bar - 1]) else osc_val
    diff = osc_val - osc_prev
    is_rising = 1.0 if diff > 0 else 0.0

    # Step 5: Kernels on the oscillator
    # Build a clean osc source (replace NaN with 0 for kernel computation)
    osc_clean = np.where(np.isnan(osc_arr), 0.0, osc_arr)

    kernel_fast_val = rq_kernel_at(osc_clean, bar, float(osc_fast_lookback), osc_fast_weight, osc_fast_start)
    kernel_slow_val = rq_kernel_at(osc_clean, bar, float(osc_slow_lookback), osc_slow_weight, osc_slow_start)

    # Rising detection for kernel lines on osc
    if bar >= 1:
        kf_prev = rq_kernel_at(osc_clean, bar - 1, float(osc_fast_lookback), osc_fast_weight, osc_fast_start)
        ks_prev = rq_kernel_at(osc_clean, bar - 1, float(osc_slow_lookback), osc_slow_weight, osc_slow_start)
    else:
        kf_prev = kernel_fast_val
        ks_prev = kernel_slow_val

    fast_rising = 1.0 if kernel_fast_val > kf_prev else 0.0
    slow_rising = 1.0 if kernel_slow_val > ks_prev else 0.0

    return {
        "osc": osc_val,
        "diff": diff,
        "is_rising": is_rising,
        "kernel_fast": kernel_fast_val,
        "kernel_slow": kernel_slow_val,
        "fast_rising": fast_rising,
        "slow_rising": slow_rising,
    }


# ─── Full series ──────────────────────────────────────────────────────

def kernel_ao_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute Kernel AO over all bars.

    Args:
        df: Full DataFrame with 'close' column.
        params: See _extract_params for keys and defaults.

    Returns:
        dict of output_name -> list[float|None], same length as df.
    """
    (
        fast_lookback, fast_weight, fast_start, fast_smooth, fast_smooth_period,
        slow_lookback, slow_weight, slow_start, slow_smooth, slow_smooth_period,
        osc_fast_lookback, osc_fast_weight, osc_fast_start,
        osc_slow_lookback, osc_slow_weight, osc_slow_start,
    ) = _extract_params(params)

    n = len(df)
    empty: dict[str, list[float | None]] = {k: [None] * n for k in KERNEL_AO_EMPTY}

    if n < 3:
        return empty

    closes = df["close"].values

    # Step 1-2: Fast and slow kernels on close prices
    fast_raw = rq_kernel_series(closes, float(fast_lookback), fast_weight, fast_start)
    fast_k = _sma_smooth(fast_raw, fast_smooth_period) if fast_smooth else fast_raw

    slow_raw = rq_kernel_series(closes, float(slow_lookback), slow_weight, slow_start)
    slow_k = _sma_smooth(slow_raw, slow_smooth_period) if slow_smooth else slow_raw

    # Step 3: Oscillator
    osc_arr = np.full(n, np.nan)
    for i in range(n):
        if not np.isnan(fast_k[i]) and not np.isnan(slow_k[i]):
            osc_arr[i] = fast_k[i] - slow_k[i]

    # Step 5: Kernels on oscillator (replace NaN with 0 for kernel input)
    osc_clean = np.where(np.isnan(osc_arr), 0.0, osc_arr)
    kf_on_osc = rq_kernel_series(osc_clean, float(osc_fast_lookback), osc_fast_weight, osc_fast_start)
    ks_on_osc = rq_kernel_series(osc_clean, float(osc_slow_lookback), osc_slow_weight, osc_slow_start)

    # Build output
    out_osc: list[float | None] = [None] * n
    out_diff: list[float | None] = [None] * n
    out_rising: list[float | None] = [None] * n
    out_kf: list[float | None] = [None] * n
    out_ks: list[float | None] = [None] * n
    out_kf_rising: list[float | None] = [None] * n
    out_ks_rising: list[float | None] = [None] * n

    for i in range(n):
        if np.isnan(osc_arr[i]):
            continue

        osc_val = float(osc_arr[i])
        out_osc[i] = osc_val

        # diff and is_rising
        if i >= 1 and not np.isnan(osc_arr[i - 1]):
            d = osc_val - float(osc_arr[i - 1])
            out_diff[i] = d
            out_rising[i] = 1.0 if d > 0 else 0.0
        else:
            out_diff[i] = 0.0
            out_rising[i] = 0.0

        # Kernel on osc values
        kf_val = float(kf_on_osc[i]) if not np.isnan(kf_on_osc[i]) else None
        ks_val = float(ks_on_osc[i]) if not np.isnan(ks_on_osc[i]) else None
        out_kf[i] = kf_val
        out_ks[i] = ks_val

        # Rising for kernel lines
        if i >= 1:
            kf_prev = float(kf_on_osc[i - 1]) if not np.isnan(kf_on_osc[i - 1]) else kf_val
            ks_prev = float(ks_on_osc[i - 1]) if not np.isnan(ks_on_osc[i - 1]) else ks_val
            out_kf_rising[i] = 1.0 if kf_val is not None and kf_prev is not None and kf_val > kf_prev else 0.0
            out_ks_rising[i] = 1.0 if ks_val is not None and ks_prev is not None and ks_val > ks_prev else 0.0
        else:
            out_kf_rising[i] = 0.0
            out_ks_rising[i] = 0.0

    return {
        "osc": out_osc,
        "diff": out_diff,
        "is_rising": out_rising,
        "kernel_fast": out_kf,
        "kernel_slow": out_ks,
        "fast_rising": out_kf_rising,
        "slow_rising": out_ks_rising,
    }
