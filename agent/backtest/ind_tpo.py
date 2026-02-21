"""TPO (Time Price Opportunity / Market Profile) Indicator.

Rolling-window TPO that works on any timeframe without session detection.
Computes Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL)
from a histogram of time spent at each price level.

Algorithm:
1. Take bars within a rolling lookback window
2. Divide the window's price range into equal-sized bins
3. Count which bins each bar's High-Low range covers (TPO count per bin)
4. POC = midpoint of bin with highest TPO count
5. Value Area = expand from POC bin until value_area_pct% of total TPOs included
6. VAH = top of highest VA bin, VAL = bottom of lowest VA bin
"""

import numpy as np
import pandas as pd


TPO_EMPTY: dict[str, float] = {
    "poc": 0.0,
    "vah": 0.0,
    "val": 0.0,
}


def _compute_tpo(
    highs: np.ndarray,
    lows: np.ndarray,
    num_bins: int,
    value_area_pct: float,
) -> dict[str, float]:
    """Compute TPO profile for a window of bars.

    Args:
        highs: High prices for the window
        lows: Low prices for the window
        num_bins: Number of price histogram bins
        value_area_pct: Percentage of TPOs for Value Area (e.g. 70.0)

    Returns:
        dict with poc, vah, val
    """
    range_high = float(np.max(highs))
    range_low = float(np.min(lows))

    if range_high <= range_low or num_bins < 2:
        mid = (range_high + range_low) / 2.0
        return {"poc": mid, "vah": range_high, "val": range_low}

    bin_size = (range_high - range_low) / num_bins
    tpo_counts = np.zeros(num_bins, dtype=np.int64)

    # Count TPOs: for each bar, increment bins that its H-L range covers
    for i in range(len(highs)):
        lo_bin = int((lows[i] - range_low) / bin_size)
        hi_bin = int((highs[i] - range_low) / bin_size)
        # Clamp to valid range
        lo_bin = max(0, min(lo_bin, num_bins - 1))
        hi_bin = max(0, min(hi_bin, num_bins - 1))
        tpo_counts[lo_bin : hi_bin + 1] += 1

    # POC: bin with highest TPO count (ties: closest to price center)
    max_count = int(np.max(tpo_counts))
    center_bin = num_bins / 2.0
    poc_bin = 0
    best_dist = float("inf")
    for b in range(num_bins):
        if tpo_counts[b] == max_count:
            dist = abs(b + 0.5 - center_bin)
            if dist < best_dist:
                best_dist = dist
                poc_bin = b

    poc = range_low + (poc_bin + 0.5) * bin_size

    # Value Area: expand from POC bin until value_area_pct% of total TPOs
    total_tpo = int(np.sum(tpo_counts))
    va_threshold = total_tpo * (value_area_pct / 100.0)

    va_lo = poc_bin
    va_hi = poc_bin
    va_tpo = int(tpo_counts[poc_bin])

    while va_tpo < va_threshold:
        can_go_up = va_hi + 1 < num_bins
        can_go_down = va_lo - 1 >= 0

        if not can_go_up and not can_go_down:
            break

        up_count = int(tpo_counts[va_hi + 1]) if can_go_up else -1
        down_count = int(tpo_counts[va_lo - 1]) if can_go_down else -1

        if up_count >= down_count:
            va_hi += 1
            va_tpo += up_count
        else:
            va_lo -= 1
            va_tpo += down_count

    vah = range_low + (va_hi + 1) * bin_size
    val = range_low + va_lo * bin_size

    return {"poc": poc, "vah": vah, "val": val}


def tpo_at(df: pd.DataFrame, params: dict) -> dict[str, float]:
    """Compute TPO at the last bar of df (point-in-time, no look-ahead).

    Args:
        df: DataFrame with columns 'high', 'low' (sliced up to current bar)
        params: {lookback, num_bins, value_area_pct}

    Returns:
        dict with poc, vah, val
    """
    lookback = params.get("lookback", 50)
    num_bins = params.get("num_bins", 24)
    value_area_pct = params.get("value_area_pct", 70.0)

    n = len(df)
    if n < 2:
        return dict(TPO_EMPTY)

    start = max(0, n - lookback)
    window = df.iloc[start:n]
    highs = window["high"].values
    lows = window["low"].values

    return _compute_tpo(highs, lows, num_bins, value_area_pct)


def tpo_series(df: pd.DataFrame, params: dict) -> dict[str, list[float | None]]:
    """Compute TPO over the full bar array (vectorised rolling window).

    Args:
        df: Full DataFrame with columns 'high', 'low'
        params: {lookback, num_bins, value_area_pct}

    Returns:
        dict of output_name -> list[float|None], same length as df
    """
    lookback = params.get("lookback", 50)
    num_bins = params.get("num_bins", 24)
    value_area_pct = params.get("value_area_pct", 70.0)

    n = len(df)
    poc_list: list[float | None] = [None] * n
    vah_list: list[float | None] = [None] * n
    val_list: list[float | None] = [None] * n

    if n == 0:
        return {"poc": poc_list, "vah": vah_list, "val": val_list}

    highs = df["high"].values
    lows = df["low"].values

    # Need at least 2 bars for a meaningful profile
    for i in range(1, n):
        start = max(0, i - lookback + 1)
        result = _compute_tpo(highs[start : i + 1], lows[start : i + 1], num_bins, value_area_pct)
        poc_list[i] = result["poc"]
        vah_list[i] = result["vah"]
        val_list[i] = result["val"]

    return {"poc": poc_list, "vah": vah_list, "val": val_list}
