NAME = "KeltnerChannel"
KEYWORDS = ["keltner", "keltner channel", "kc", "kelt", "keltner bands", "keltner envelope"]
EMPTY_RESULT = {"upper": 0.0, "middle": 0.0, "lower": 0.0, "width": 0.0}


def compute(df, params):
    """Compute Keltner Channel from OHLCV DataFrame.

    Keltner Channel plots an EMA middle line with upper/lower bands offset
    by a multiple of ATR. When price breaks outside the bands it signals
    strong momentum; when price reverts inside it signals mean-reversion.

    Args:
        df: pandas DataFrame with columns: open, high, low, close, volume
        params: dict with keys ema_period, atr_period, atr_factor

    Returns:
        dict with upper, middle, lower, width (band width as % of middle)
    """
    import pandas_ta as ta
    import numpy as np

    ema_period = max(int(params.get("ema_period", 20)), 10)
    atr_period = max(int(params.get("atr_period", 10)), 3)
    atr_factor = max(float(params.get("atr_factor", 2.0)), 1.0)

    if len(df) < max(ema_period, atr_period) + 2:
        return dict(EMPTY_RESULT)

    ema = ta.ema(df["close"], length=ema_period)
    atr = ta.atr(df["high"], df["low"], df["close"], length=atr_period)

    if ema is None or atr is None or ema.empty or atr.empty:
        return dict(EMPTY_RESULT)

    upper = ema + atr_factor * atr
    lower = ema - atr_factor * atr

    # MQL5 version uses PLOT_SHIFT=1 (values shifted forward by 1 bar).
    # For a live signal we therefore read the second-to-last completed value,
    # which corresponds to the value drawn on the last visible bar.
    idx = -2 if len(df) >= max(ema_period, atr_period) + 3 else -1

    mid_val = ema.iloc[idx]
    upp_val = upper.iloc[idx]
    low_val = lower.iloc[idx]

    if np.isnan(mid_val) or np.isnan(upp_val) or np.isnan(low_val):
        return dict(EMPTY_RESULT)

    width = ((upp_val - low_val) / mid_val * 100.0) if mid_val != 0 else 0.0

    return {
        "upper": round(float(upp_val), 6),
        "middle": round(float(mid_val), 6),
        "lower": round(float(low_val), 6),
        "width": round(float(width), 4),
    }