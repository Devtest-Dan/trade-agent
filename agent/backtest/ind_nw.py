"""Nadaraya-Watson Kernel Indicators — faithful PineScript conversion.

Two indicators:
1. NW_RQ_Kernel — Rational Quadratic Kernel regression with direction signals
2. NW_Envelope — Kernel regression with ATR-based envelope bands

Based on PineScript by jdehorty:
- "Nadaraya-Watson: Rational Quadratic Kernel (Non-Repainting)"
- "Nadaraya-Watson: Envelope (Non-Repainting)"
"""

import math
from typing import Any

import numpy as np
import pandas as pd


# ─── Core Kernel Function ─────────────────────────────────────────────
# Rational Quadratic kernel weight:
#   w(i) = (1 + i² / (2 · r · h²))^(-r)
# where i = lag, h = bandwidth (lookback), r = relative weighting (alpha)


def _rq_weight(lag: int, h: float, r: float) -> float:
    """Compute Rational Quadratic kernel weight for a given lag."""
    return (1.0 + (lag * lag) / (h * h * 2.0 * r)) ** (-r)


def rq_kernel_at(src: np.ndarray, bar_idx: int, h: float, r: float, x_0: int) -> float:
    """Compute RQ kernel regression estimate at a single bar.

    Matches PineScript: for i = 0 to size + x_0, src[i] * w(i) / sum(w)
    where size ≈ 1 in PineScript (array.size of single source),
    so loop range is 0..x_0+1. For the envelope library version,
    we use a larger range to match the imported library behavior.

    Args:
        src: Full source array (e.g., close prices)
        bar_idx: Current bar index to compute estimate at
        h: Lookback window (bandwidth)
        r: Relative weighting (alpha)
        x_0: Start regression bar offset
    """
    max_lookback = min(bar_idx + 1, 500 + x_0)
    weighted_sum = 0.0
    total_weight = 0.0

    for i in range(max_lookback):
        idx = bar_idx - i
        if idx < 0:
            break
        w = _rq_weight(i, h, r)
        weighted_sum += src[idx] * w
        total_weight += w

    if total_weight == 0:
        return float(src[bar_idx])
    return weighted_sum / total_weight


def rq_kernel_series(src: np.ndarray, h: float, r: float, x_0: int) -> np.ndarray:
    """Compute RQ kernel regression for every bar in the series."""
    n = len(src)
    result = np.full(n, np.nan)
    for bar_idx in range(n):
        result[bar_idx] = rq_kernel_at(src, bar_idx, h, r, x_0)
    return result


# ─── RMA (Running Moving Average / Wilder's Smoothing) ────────────────
# rma = (prev_rma * (length - 1) + current) / length


def _rma(values: np.ndarray, length: int) -> np.ndarray:
    """Wilder's smoothing (RMA), matching PineScript ta.rma."""
    n = len(values)
    result = np.full(n, np.nan)
    if n < length:
        return result

    # Seed with SMA of first `length` values
    result[length - 1] = np.mean(values[:length])
    alpha = 1.0 / length

    for i in range(length, n):
        result[i] = result[i - 1] * (1 - alpha) + values[i] * alpha

    return result


# ─── True Range on kernel-smoothed OHLC ───────────────────────────────
# Matches PineScript kernel_atr():
#   trueRange = na(high[1]) ? high-low : max(high-low, |high-close[1]|, |low-close[1]|)
#   kernel_atr = ta.rma(trueRange, length)


def _kernel_atr(yhat_high: np.ndarray, yhat_low: np.ndarray,
                yhat_close: np.ndarray, length: int) -> np.ndarray:
    """Compute ATR on kernel-smoothed OHLC values."""
    n = len(yhat_high)
    tr = np.full(n, np.nan)

    for i in range(n):
        hl = yhat_high[i] - yhat_low[i]
        if i == 0 or np.isnan(yhat_close[i - 1]):
            tr[i] = hl
        else:
            hc = abs(yhat_high[i] - yhat_close[i - 1])
            lc = abs(yhat_low[i] - yhat_close[i - 1])
            tr[i] = max(hl, hc, lc)

    return _rma(tr, length)


# ═══════════════════════════════════════════════════════════════════════
# Indicator 1: NW Rational Quadratic Kernel
# ═══════════════════════════════════════════════════════════════════════

KERNEL_EMPTY: dict[str, float] = {
    "value": 0.0,
    "is_bullish": 0.0,
    "is_bearish": 0.0,
    "smooth_bullish": 0.0,
    "smooth_bearish": 0.0,
}


def nw_rq_kernel_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute NW RQ Kernel at the last bar of the slice.

    PineScript params: src=close, h=8, r=8, x_0=25, smoothColors=false, lag=2
    """
    h = params.get("lookback_window", params.get("h", 8.0))
    r = params.get("relative_weighting", params.get("r", 8.0))
    x_0 = params.get("start_bar", params.get("x_0", 25))
    lag = params.get("lag", 2)

    closes = df["close"].values
    n = len(df)

    if n < 3:
        return dict(KERNEL_EMPTY)

    bar_idx = n - 1

    # Main estimate and lagged estimate
    yhat1 = rq_kernel_at(closes, bar_idx, h, r, x_0)
    yhat2 = rq_kernel_at(closes, bar_idx, h - lag, r, x_0)

    # Direction: compare current vs previous estimates
    yhat1_prev = rq_kernel_at(closes, bar_idx - 1, h, r, x_0) if bar_idx >= 1 else yhat1
    yhat1_prev2 = rq_kernel_at(closes, bar_idx - 2, h, r, x_0) if bar_idx >= 2 else yhat1_prev

    # Rate of change signals (PineScript: isBullish = yhat1[1] < yhat1)
    is_bullish = 1.0 if yhat1_prev < yhat1 else 0.0
    is_bearish = 1.0 if yhat1_prev > yhat1 else 0.0

    # Crossover signals (smooth mode)
    yhat2_prev = rq_kernel_at(closes, bar_idx - 1, h - lag, r, x_0) if bar_idx >= 1 else yhat2
    smooth_bullish = 1.0 if yhat2 > yhat1 else 0.0
    smooth_bearish = 1.0 if yhat2 < yhat1 else 0.0

    return {
        "value": yhat1,
        "is_bullish": is_bullish,
        "is_bearish": is_bearish,
        "smooth_bullish": smooth_bullish,
        "smooth_bearish": smooth_bearish,
    }


def nw_rq_kernel_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute NW RQ Kernel over all bars."""
    h = params.get("lookback_window", params.get("h", 8.0))
    r = params.get("relative_weighting", params.get("r", 8.0))
    x_0 = params.get("start_bar", params.get("x_0", 25))
    lag = params.get("lag", 2)

    closes = df["close"].values
    n = len(df)

    out_value: list[float | None] = [None] * n
    out_bull: list[float | None] = [None] * n
    out_bear: list[float | None] = [None] * n

    if n < 2:
        return {"value": out_value, "is_bullish": out_bull, "is_bearish": out_bear}

    # Compute main kernel series
    yhat1 = rq_kernel_series(closes, h, r, x_0)

    for i in range(n):
        out_value[i] = float(yhat1[i]) if not np.isnan(yhat1[i]) else None

    for i in range(1, n):
        if out_value[i] is not None and out_value[i - 1] is not None:
            out_bull[i] = 1.0 if yhat1[i - 1] < yhat1[i] else 0.0
            out_bear[i] = 1.0 if yhat1[i - 1] > yhat1[i] else 0.0

    return {"value": out_value, "is_bullish": out_bull, "is_bearish": out_bear}


# ═══════════════════════════════════════════════════════════════════════
# Indicator 2: NW Envelope
# ═══════════════════════════════════════════════════════════════════════

ENVELOPE_EMPTY: dict[str, float] = {
    "yhat": 0.0,
    "upper_far": 0.0,
    "upper_avg": 0.0,
    "upper_near": 0.0,
    "lower_near": 0.0,
    "lower_avg": 0.0,
    "lower_far": 0.0,
    "is_bullish": 0.0,
    "is_bearish": 0.0,
}


def nw_envelope_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute NW Envelope at the last bar.

    PineScript params: h=8, alpha=8, x_0=25, atr_length=60, nearFactor=1.5, farFactor=8.0
    """
    h = params.get("lookback_window", params.get("h", 8))
    alpha = params.get("relative_weighting", params.get("alpha", 8.0))
    x_0 = params.get("start_bar", params.get("x_0", 25))
    atr_length = params.get("atr_length", 60)
    near_factor = params.get("near_factor", params.get("nearFactor", 1.5))
    far_factor = params.get("far_factor", params.get("farFactor", 8.0))

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    if n < max(atr_length + 1, 10):
        return dict(ENVELOPE_EMPTY)

    # Compute kernel series for close, high, low (need series for kernel ATR)
    yhat_close = rq_kernel_series(closes, h, alpha, x_0)
    yhat_high = rq_kernel_series(highs, h, alpha, x_0)
    yhat_low = rq_kernel_series(lows, h, alpha, x_0)

    # Kernel ATR
    ktr = _kernel_atr(yhat_high, yhat_low, yhat_close, atr_length)

    bar_idx = n - 1
    yhat = float(yhat_close[bar_idx])
    ktr_val = float(ktr[bar_idx]) if not np.isnan(ktr[bar_idx]) else 0.0

    # Bands
    upper_far = yhat + far_factor * ktr_val
    upper_near = yhat + near_factor * ktr_val
    upper_avg = (upper_far + upper_near) / 2.0
    lower_near = yhat - near_factor * ktr_val
    lower_far = yhat - far_factor * ktr_val
    lower_avg = (lower_far + lower_near) / 2.0

    # Direction
    yhat_prev = float(yhat_close[bar_idx - 1]) if bar_idx >= 1 and not np.isnan(yhat_close[bar_idx - 1]) else yhat
    is_bullish = 1.0 if yhat > yhat_prev else 0.0
    is_bearish = 1.0 if yhat < yhat_prev else 0.0

    return {
        "yhat": yhat,
        "upper_far": upper_far,
        "upper_avg": upper_avg,
        "upper_near": upper_near,
        "lower_near": lower_near,
        "lower_avg": lower_avg,
        "lower_far": lower_far,
        "is_bullish": is_bullish,
        "is_bearish": is_bearish,
    }


def nw_envelope_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute NW Envelope over all bars."""
    h = params.get("lookback_window", params.get("h", 8))
    alpha = params.get("relative_weighting", params.get("alpha", 8.0))
    x_0 = params.get("start_bar", params.get("x_0", 25))
    atr_length = params.get("atr_length", 60)
    near_factor = params.get("near_factor", params.get("nearFactor", 1.5))
    far_factor = params.get("far_factor", params.get("farFactor", 8.0))

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    empty = {k: [None] * n for k in ENVELOPE_EMPTY}
    if n < max(atr_length + 1, 10):
        return empty

    # Kernel series
    yhat_close = rq_kernel_series(closes, h, alpha, x_0)
    yhat_high = rq_kernel_series(highs, h, alpha, x_0)
    yhat_low = rq_kernel_series(lows, h, alpha, x_0)

    # Kernel ATR
    ktr = _kernel_atr(yhat_high, yhat_low, yhat_close, atr_length)

    # Build output arrays
    out: dict[str, list[float | None]] = {k: [None] * n for k in ENVELOPE_EMPTY}

    for i in range(n):
        yhat = float(yhat_close[i]) if not np.isnan(yhat_close[i]) else None
        ktr_val = float(ktr[i]) if not np.isnan(ktr[i]) else None

        if yhat is None or ktr_val is None:
            continue

        out["yhat"][i] = yhat
        out["upper_far"][i] = yhat + far_factor * ktr_val
        out["upper_near"][i] = yhat + near_factor * ktr_val
        out["upper_avg"][i] = (out["upper_far"][i] + out["upper_near"][i]) / 2.0
        out["lower_near"][i] = yhat - near_factor * ktr_val
        out["lower_far"][i] = yhat - far_factor * ktr_val
        out["lower_avg"][i] = (out["lower_far"][i] + out["lower_near"][i]) / 2.0

        # Direction
        if i > 0 and out["yhat"][i - 1] is not None:
            out["is_bullish"][i] = 1.0 if yhat > out["yhat"][i - 1] else 0.0
            out["is_bearish"][i] = 1.0 if yhat < out["yhat"][i - 1] else 0.0

    return out
