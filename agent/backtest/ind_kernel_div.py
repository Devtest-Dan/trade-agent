"""Kernel AO Divergence Indicator — faithful PineScript conversion.

Detects divergences between price and the Kernel AO oscillator.

Kernel AO Oscillator:
    fast = RQ_Kernel(close, h=5, r=8, x_0=25), SMA smoothed
    slow = RQ_Kernel(close, h=34, r=3, x_0=120), SMA smoothed
    osc  = fast - slow

Divergence detection uses zero-crossings of the oscillator to identify
swing highs/lows, then compares price swings vs oscillator swings.

Signal line: Nadaraya-Watson RQ kernel on close (h=8, r=8, x_0=25).
"""

from typing import Any

import numpy as np
import pandas as pd

from .ind_nw import rq_kernel_at, rq_kernel_series


# ─── SMA helper ──────────────────────────────────────────────────────

def _sma(values: np.ndarray, length: int) -> np.ndarray:
    """Simple moving average matching PineScript ta.sma."""
    n = len(values)
    result = np.full(n, np.nan)
    if n < length:
        return result
    cumsum = np.cumsum(values)
    result[length - 1] = cumsum[length - 1] / length
    for i in range(length, n):
        result[i] = (cumsum[i] - cumsum[i - length]) / length
    return result


# ─── Oscillator range helpers ────────────────────────────────────────

def _find_lowest_osc(osc_values: np.ndarray, from_bar: int, lookback: int) -> float:
    """Find minimum oscillator value in range [from_bar - lookback + 1, from_bar].

    Bars are clamped to valid indices. Returns inf if no valid bars.
    """
    start = max(0, from_bar - lookback + 1)
    end = from_bar + 1  # exclusive
    if start >= end or start >= len(osc_values):
        return float("inf")
    segment = osc_values[start:end]
    valid = segment[~np.isnan(segment)]
    if len(valid) == 0:
        return float("inf")
    return float(np.min(valid))


def _find_highest_osc(osc_values: np.ndarray, from_bar: int, lookback: int) -> float:
    """Find maximum oscillator value in range [from_bar - lookback + 1, from_bar].

    Bars are clamped to valid indices. Returns -inf if no valid bars.
    """
    start = max(0, from_bar - lookback + 1)
    end = from_bar + 1  # exclusive
    if start >= end or start >= len(osc_values):
        return float("-inf")
    segment = osc_values[start:end]
    valid = segment[~np.isnan(segment)]
    if len(valid) == 0:
        return float("-inf")
    return float(np.max(valid))


# ─── Empty output template ───────────────────────────────────────────

KERNEL_DIV_EMPTY: dict[str, float] = {
    "osc": 0.0,
    "bull_reg_div": 0.0,
    "bull_hid_div": 0.0,
    "bear_reg_div": 0.0,
    "bear_hid_div": 0.0,
    "signal_line": 0.0,
    "swing_high_bar": 0.0,
    "swing_low_bar": 0.0,
    "swing_high_price": 0.0,
    "swing_low_price": 0.0,
}


# ─── Core series computation ─────────────────────────────────────────

def _compute_kernel_div_series(
    closes: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    fast_h: float,
    fast_r: float,
    fast_x0: int,
    fast_sma_len: int,
    slow_h: float,
    slow_r: float,
    slow_x0: int,
    slow_sma_len: int,
    signal_h: float,
    signal_r: float,
    signal_x0: int,
) -> dict[str, np.ndarray]:
    """Compute Kernel AO Divergence over all bars.

    Returns dict of numpy arrays, one per output key.
    """
    n = len(closes)

    # --- Kernel AO Oscillator ---
    fast_kernel_raw = rq_kernel_series(closes, fast_h, fast_r, fast_x0)
    slow_kernel_raw = rq_kernel_series(closes, slow_h, slow_r, slow_x0)

    fast_kernel = _sma(fast_kernel_raw, fast_sma_len)
    slow_kernel = _sma(slow_kernel_raw, slow_sma_len)

    osc = fast_kernel - slow_kernel

    # --- Signal line ---
    signal_line = rq_kernel_series(closes, signal_h, signal_r, signal_x0)

    # --- Output arrays ---
    bull_reg_div = np.zeros(n)
    bull_hid_div = np.zeros(n)
    bear_reg_div = np.zeros(n)
    bear_hid_div = np.zeros(n)
    swing_high_bar_out = np.zeros(n)
    swing_low_bar_out = np.zeros(n)
    swing_high_price_out = np.zeros(n)
    swing_low_price_out = np.zeros(n)

    # --- Swing state tracking ---
    # Bars where current negative/positive range started
    negative_start = -1
    positive_start = -1

    # Tracking lowest/highest values within current negative/positive range
    lowest_val = float("inf")
    highest_val = float("-inf")
    lowest_bar = 0
    highest_bar = 0

    # Swing high/low records (bar indices into the full array)
    previous_high = 0
    current_high = 0
    previous_low = 0
    current_low = 0

    # Previous bar's oscillator for cross detection
    prev_osc = np.nan

    for i in range(n):
        curr_osc = osc[i]

        if np.isnan(curr_osc) or np.isnan(prev_osc):
            prev_osc = curr_osc
            swing_high_bar_out[i] = current_high
            swing_low_bar_out[i] = current_low
            swing_high_price_out[i] = highs[current_high] if current_high < n else 0.0
            swing_low_price_out[i] = lows[current_low] if current_low < n else 0.0
            continue

        # --- Detect zero crossings ---
        # Cross below zero: prev >= 0 and curr < 0
        cross_below = prev_osc >= 0 and curr_osc < 0
        # Cross above zero: prev <= 0 and curr > 0
        cross_above = prev_osc <= 0 and curr_osc > 0

        if cross_below:
            # Entering negative territory — record the swing high
            # The highest price high during the positive range is the swing high
            previous_high = current_high
            current_high = highest_bar
            # Reset for new negative range
            negative_start = i
            lowest_val = float("inf")
            lowest_bar = i

        if cross_above:
            # Entering positive territory — record the swing low
            previous_low = current_low
            current_low = lowest_bar
            # Reset for new positive range
            positive_start = i
            highest_val = float("-inf")
            highest_bar = i

        # --- Track lowest/highest price in current range ---
        if curr_osc < 0:
            if lows[i] < lowest_val:
                lowest_val = lows[i]
                lowest_bar = i
        elif curr_osc > 0:
            if highs[i] > highest_val:
                highest_val = highs[i]
                highest_bar = i

        # --- Divergence Logic ---
        # Current swing bar indices (offsets from current bar i)
        curr_low_bar = current_low
        prev_low_bar = previous_low
        curr_high_bar = current_high
        prev_high_bar = previous_high

        # Need valid previous swings to detect divergence
        if prev_low_bar > 0 and curr_low_bar > 0 and curr_low_bar != prev_low_bar:
            # --- Bullish divergences (price lows vs osc lows in negative ranges) ---
            # Must be in a downleg: current low bar >= current high bar
            in_downleg = curr_low_bar >= curr_high_bar

            if in_downleg:
                price_lower_low = lows[curr_low_bar] < lows[prev_low_bar]
                price_higher_low = lows[curr_low_bar] > lows[prev_low_bar]

                # Find lowest osc in previous and current negative ranges
                # Range from current high bar to previous low (previous negative range)
                range1_lookback = max(1, prev_low_bar - curr_high_bar + 1) if prev_low_bar >= curr_high_bar else max(1, prev_low_bar + 1)
                lowest1 = _find_lowest_osc(osc, prev_low_bar, range1_lookback)

                # Range from negative_start (or range start) to current bar
                if negative_start >= 0:
                    range2_lookback = max(1, i - negative_start + 1)
                else:
                    range2_lookback = max(1, i - curr_low_bar + 1)
                lowest2 = _find_lowest_osc(osc, i, range2_lookback)

                # Bullish Regular: price lower low, osc higher low
                if price_lower_low and lowest1 < lowest2:
                    bull_reg_div[i] = 1.0

                # Bullish Hidden: price higher low, osc lower low
                if price_higher_low and lowest1 > lowest2:
                    bull_hid_div[i] = 1.0

        if prev_high_bar > 0 and curr_high_bar > 0 and curr_high_bar != prev_high_bar:
            # --- Bearish divergences (price highs vs osc highs in positive ranges) ---
            # Must be in an upleg: current low bar < current high bar
            in_upleg = curr_low_bar < curr_high_bar

            if in_upleg:
                price_higher_high = highs[curr_high_bar] > highs[prev_high_bar]
                price_lower_high = highs[curr_high_bar] < highs[prev_high_bar]

                # Find highest osc in previous and current positive ranges
                range1_lookback = max(1, prev_high_bar - curr_low_bar + 1) if prev_high_bar >= curr_low_bar else max(1, prev_high_bar + 1)
                highest1 = _find_highest_osc(osc, prev_high_bar, range1_lookback)

                if positive_start >= 0:
                    range2_lookback = max(1, i - positive_start + 1)
                else:
                    range2_lookback = max(1, i - curr_high_bar + 1)
                highest2 = _find_highest_osc(osc, i, range2_lookback)

                # Bearish Regular: price higher high, osc lower high
                if price_higher_high and highest1 > highest2:
                    bear_reg_div[i] = 1.0

                # Bearish Hidden: price lower high, osc higher high
                if price_lower_high and highest1 < highest2:
                    bear_hid_div[i] = 1.0

        # Store swing info for this bar
        swing_high_bar_out[i] = float(current_high)
        swing_low_bar_out[i] = float(current_low)
        swing_high_price_out[i] = highs[current_high] if current_high < n else 0.0
        swing_low_price_out[i] = lows[current_low] if current_low < n else 0.0

        prev_osc = curr_osc

    return {
        "osc": osc,
        "bull_reg_div": bull_reg_div,
        "bull_hid_div": bull_hid_div,
        "bear_reg_div": bear_reg_div,
        "bear_hid_div": bear_hid_div,
        "signal_line": signal_line,
        "swing_high_bar": swing_high_bar_out,
        "swing_low_bar": swing_low_bar_out,
        "swing_high_price": swing_high_price_out,
        "swing_low_price": swing_low_price_out,
    }


# ─── Public API ──────────────────────────────────────────────────────

def kernel_div_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute Kernel AO Divergence at the last bar of df.

    Args:
        df: DataFrame with columns 'close', 'high', 'low'
        params: {
            fast_lookback (5), fast_weight (8), fast_start (25), fast_sma (5),
            slow_lookback (34), slow_weight (3), slow_start (120), slow_sma (5),
            signal_h (8), signal_r (8), signal_x0 (25)
        }

    Returns:
        dict matching KERNEL_DIV_EMPTY keys
    """
    n = len(df)
    if n < 5:
        return dict(KERNEL_DIV_EMPTY)

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    fast_h = params.get("fast_lookback", 5.0)
    fast_r = params.get("fast_weight", 8.0)
    fast_x0 = params.get("fast_start", 25)
    fast_sma_len = params.get("fast_sma", 5)
    slow_h = params.get("slow_lookback", 34.0)
    slow_r = params.get("slow_weight", 3.0)
    slow_x0 = params.get("slow_start", 120)
    slow_sma_len = params.get("slow_sma", 5)
    signal_h = params.get("signal_h", 8.0)
    signal_r = params.get("signal_r", 8.0)
    signal_x0 = params.get("signal_x0", 25)

    arrays = _compute_kernel_div_series(
        closes, highs, lows,
        fast_h, fast_r, fast_x0, fast_sma_len,
        slow_h, slow_r, slow_x0, slow_sma_len,
        signal_h, signal_r, signal_x0,
    )

    last = n - 1
    result: dict[str, float] = {}
    for key in KERNEL_DIV_EMPTY:
        val = arrays[key][last]
        result[key] = float(val) if not np.isnan(val) else 0.0
    return result


def kernel_div_series(
    df: pd.DataFrame, params: dict[str, Any]
) -> dict[str, list[float | None]]:
    """Compute Kernel AO Divergence over all bars.

    Args:
        df: Full DataFrame with columns 'close', 'high', 'low'
        params: Same as kernel_div_at

    Returns:
        dict of output_name -> list[float|None], same length as df
    """
    n = len(df)
    empty = {k: [None] * n for k in KERNEL_DIV_EMPTY}

    if n < 5:
        return empty

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    fast_h = params.get("fast_lookback", 5.0)
    fast_r = params.get("fast_weight", 8.0)
    fast_x0 = params.get("fast_start", 25)
    fast_sma_len = params.get("fast_sma", 5)
    slow_h = params.get("slow_lookback", 34.0)
    slow_r = params.get("slow_weight", 3.0)
    slow_x0 = params.get("slow_start", 120)
    slow_sma_len = params.get("slow_sma", 5)
    signal_h = params.get("signal_h", 8.0)
    signal_r = params.get("signal_r", 8.0)
    signal_x0 = params.get("signal_x0", 25)

    arrays = _compute_kernel_div_series(
        closes, highs, lows,
        fast_h, fast_r, fast_x0, fast_sma_len,
        slow_h, slow_r, slow_x0, slow_sma_len,
        signal_h, signal_r, signal_x0,
    )

    out: dict[str, list[float | None]] = {}
    for key in KERNEL_DIV_EMPTY:
        arr = arrays[key]
        out[key] = [
            float(arr[i]) if not np.isnan(arr[i]) else None
            for i in range(n)
        ]
    return out
