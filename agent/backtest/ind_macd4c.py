"""MACD 4-Colour Indicator — faithful PineScript conversion.

Computes MACD (fast EMA - slow EMA) and assigns one of four colour codes
based on direction and position relative to zero:
    1 = lime   (above zero, rising)
    2 = green  (above zero, falling)
    3 = maroon (below zero, falling)
    4 = red    (below zero, rising)
"""

import pandas as pd
import pandas_ta as ta


MACD4C_EMPTY: dict[str, float] = {
    "value": 0.0,
    "color": 0.0,
    "above_zero": 0.0,
    "rising": 0.0,
}


def _color_code(curr: float, prev: float) -> tuple[float, float, float]:
    """Return (color, above_zero, rising) for a MACD value pair."""
    above_zero = 1.0 if curr > 0 else 0.0
    rising = 1.0 if curr > prev else 0.0

    if curr > 0:
        color = 1.0 if curr > prev else 2.0   # lime / green
    else:
        color = 3.0 if curr < prev else 4.0   # maroon / red

    return color, above_zero, rising


def macd4c_at(df: pd.DataFrame, params: dict) -> dict[str, float]:
    """Compute MACD 4C at the last bar of df (point-in-time, no look-ahead).

    Args:
        df: DataFrame with column 'close' (sliced up to current bar)
        params: {fast, slow}

    Returns:
        dict with value, color, above_zero, rising
    """
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)

    n = len(df)
    if n < slow + 1:
        return dict(MACD4C_EMPTY)

    close = df["close"]
    ema_fast = ta.ema(close, length=fast)
    ema_slow = ta.ema(close, length=slow)

    if ema_fast is None or ema_slow is None:
        return dict(MACD4C_EMPTY)

    curr_macd = float(ema_fast.iloc[-1] - ema_slow.iloc[-1])
    prev_macd = float(ema_fast.iloc[-2] - ema_slow.iloc[-2])

    color, above_zero, rising = _color_code(curr_macd, prev_macd)

    return {
        "value": curr_macd,
        "color": color,
        "above_zero": above_zero,
        "rising": rising,
    }


def macd4c_series(df: pd.DataFrame, params: dict) -> dict[str, list[float | None]]:
    """Compute MACD 4C over the full bar array.

    Args:
        df: Full DataFrame with column 'close'
        params: {fast, slow}

    Returns:
        dict of output_name -> list[float|None], same length as df
    """
    fast = params.get("fast", 12)
    slow = params.get("slow", 26)

    n = len(df)
    value_list: list[float | None] = [None] * n
    color_list: list[float | None] = [None] * n
    above_zero_list: list[float | None] = [None] * n
    rising_list: list[float | None] = [None] * n

    if n < slow + 1:
        return {
            "value": value_list,
            "color": color_list,
            "above_zero": above_zero_list,
            "rising": rising_list,
        }

    close = df["close"]
    ema_fast = ta.ema(close, length=fast)
    ema_slow = ta.ema(close, length=slow)

    if ema_fast is None or ema_slow is None:
        return {
            "value": value_list,
            "color": color_list,
            "above_zero": above_zero_list,
            "rising": rising_list,
        }

    macd_vals = ema_fast - ema_slow

    for i in range(slow, n):
        curr = float(macd_vals.iloc[i])
        prev = float(macd_vals.iloc[i - 1])

        color, above_zero, rising = _color_code(curr, prev)

        value_list[i] = curr
        color_list[i] = color
        above_zero_list[i] = above_zero
        rising_list[i] = rising

    return {
        "value": value_list,
        "color": color_list,
        "above_zero": above_zero_list,
        "rising": rising_list,
    }
