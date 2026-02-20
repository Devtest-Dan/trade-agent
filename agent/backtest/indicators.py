"""Python indicator engine for backtesting.

Computes 10 standard indicators (via pandas_ta) and 3 custom SMC indicators
from raw OHLCV bars. All computations use only past data (no look-ahead).
"""

import math
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger

from agent.indicators.custom import discover_custom_indicators
from agent.models.market import Bar

EMPTY_VALUE = 1e308  # sentinel for "no value"


OVERLAY_INDICATORS = {"EMA", "SMA", "Bollinger", "NW_Envelope", "KeltnerChannel", "SMC_Structure", "OB_FVG"}
OSCILLATOR_INDICATORS = {"RSI", "MACD", "Stochastic", "ADX", "CCI", "WilliamsR", "ATR"}


class IndicatorEngine:
    """Compute indicator values bar-by-bar from OHLCV history."""

    def __init__(self, bars: list[Bar]):
        self._bars = bars
        self._df = pd.DataFrame({
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume for b in bars],
        })
        self._cache: dict[tuple, dict[str, float]] = {}
        self._custom_modules = discover_custom_indicators()

    def compute_at(self, bar_index: int, indicator_name: str, params: dict[str, Any]) -> dict[str, float]:
        """Compute indicator at bar_index using only data [0:bar_index+1].

        Returns dict of buffer_name → value. Uses cache to avoid recomputation.
        """
        cache_key = (bar_index, indicator_name, tuple(sorted(params.items())))
        if cache_key in self._cache:
            return self._cache[cache_key]

        sliced = self._df.iloc[:bar_index + 1]
        if len(sliced) < 2:
            result = self._empty_result(indicator_name)
            self._cache[cache_key] = result
            return result

        try:
            result = self._dispatch(indicator_name, sliced, params)
        except Exception as e:
            logger.debug(f"Indicator {indicator_name} failed at bar {bar_index}: {e}")
            result = self._empty_result(indicator_name)

        self._cache[cache_key] = result
        return result

    def _dispatch(self, name: str, df: pd.DataFrame, params: dict) -> dict[str, float]:
        """Route to the correct computation function."""
        dispatch_map = {
            "RSI": self._rsi,
            "EMA": self._ema,
            "SMA": self._sma,
            "MACD": self._macd,
            "Stochastic": self._stochastic,
            "Bollinger": self._bollinger,
            "ATR": self._atr,
            "ADX": self._adx,
            "CCI": self._cci,
            "WilliamsR": self._williams_r,
            "SMC_Structure": self._smc_structure,
            "OB_FVG": self._ob_fvg,
            "NW_Envelope": self._nw_envelope,
        }
        func = dispatch_map.get(name)
        if not func:
            # Fallback to custom indicator modules
            custom_mod = self._custom_modules.get(name)
            if custom_mod:
                return custom_mod.compute(df, params)
            raise ValueError(f"Unknown indicator: {name}")
        return func(df, params)

    def _empty_result(self, name: str) -> dict[str, float]:
        """Return empty/NaN result for an indicator."""
        outputs = {
            "RSI": {"value": 50.0},
            "EMA": {"value": 0.0},
            "SMA": {"value": 0.0},
            "MACD": {"macd": 0.0, "signal": 0.0},
            "Stochastic": {"k": 50.0, "d": 50.0},
            "Bollinger": {"upper": 0.0, "middle": 0.0, "lower": 0.0},
            "ATR": {"value": 0.0},
            "ADX": {"adx": 0.0, "plus_di": 0.0, "minus_di": 0.0},
            "CCI": {"value": 0.0},
            "WilliamsR": {"value": -50.0},
            "SMC_Structure": {
                "trend": 0.0, "swing_high": EMPTY_VALUE, "swing_low": EMPTY_VALUE,
                "strong_low": 0.0, "strong_high": 0.0, "ref_high": 0.0, "ref_low": 0.0,
                "equilibrium": 0.0, "ote_top": 0.0, "ote_bottom": 0.0,
                "swing_high_clr": 0.0, "swing_low_clr": 0.0,
            },
            "OB_FVG": {k: 0.0 for k in [
                "zz1_up", "zz1_down", "zz2_up", "zz2_down", "zz3_up", "zz3_down",
                "combined_all", "combined_partial", "ob_upper", "ob_lower",
                "overlap_upper", "overlap_lower", "ob_type", "ob_time",
                "hline_upper", "hline_lower", "fvg_upper", "fvg_lower",
                "fvg_filled", "fvg_type", "fvg_reversed",
            ]},
            "NW_Envelope": {
                "nw_bullish": 0.0, "nw_bearish": 0.0,
                "upper_far": 0.0, "upper_avg": 0.0, "upper_near": 0.0,
                "lower_near": 0.0, "lower_avg": 0.0, "lower_far": 0.0,
            },
        }
        if name in outputs:
            return outputs[name]
        # Fallback to custom indicator modules
        custom_mod = self._custom_modules.get(name)
        if custom_mod:
            return dict(custom_mod.EMPTY_RESULT)
        return {"value": 0.0}

    # --- Standard Indicators (via pandas_ta) ---

    def _rsi(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        result = ta.rsi(df["close"], length=period)
        if result is None or result.empty:
            return {"value": 50.0}
        val = result.iloc[-1]
        return {"value": float(val) if not pd.isna(val) else 50.0}

    def _ema(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        result = ta.ema(df["close"], length=period)
        if result is None or result.empty:
            return {"value": float(df["close"].iloc[-1])}
        val = result.iloc[-1]
        return {"value": float(val) if not pd.isna(val) else float(df["close"].iloc[-1])}

    def _sma(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        result = ta.sma(df["close"], length=period)
        if result is None or result.empty:
            return {"value": float(df["close"].iloc[-1])}
        val = result.iloc[-1]
        return {"value": float(val) if not pd.isna(val) else float(df["close"].iloc[-1])}

    def _macd(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        fast = params.get("fast_ema", 12)
        slow = params.get("slow_ema", 26)
        sig = params.get("signal", 9)
        result = ta.macd(df["close"], fast=fast, slow=slow, signal=sig)
        if result is None or result.empty:
            return {"macd": 0.0, "signal": 0.0}
        macd_val = result.iloc[-1, 0]
        sig_val = result.iloc[-1, 2]  # MACDs_X_Y_Z
        return {
            "macd": float(macd_val) if not pd.isna(macd_val) else 0.0,
            "signal": float(sig_val) if not pd.isna(sig_val) else 0.0,
        }

    def _stochastic(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        k_period = params.get("k_period", 5)
        d_period = params.get("d_period", 3)
        slowing = params.get("slowing", 3)
        result = ta.stoch(df["high"], df["low"], df["close"], k=k_period, d=d_period, smooth_k=slowing)
        if result is None or result.empty:
            return {"k": 50.0, "d": 50.0}
        k_val = result.iloc[-1, 0]
        d_val = result.iloc[-1, 1]
        return {
            "k": float(k_val) if not pd.isna(k_val) else 50.0,
            "d": float(d_val) if not pd.isna(d_val) else 50.0,
        }

    def _bollinger(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 20)
        deviation = params.get("deviation", 2.0)
        result = ta.bbands(df["close"], length=period, std=deviation)
        if result is None or result.empty:
            p = float(df["close"].iloc[-1])
            return {"upper": p, "middle": p, "lower": p}
        lower = result.iloc[-1, 0]
        mid = result.iloc[-1, 1]
        upper = result.iloc[-1, 2]
        return {
            "upper": float(upper) if not pd.isna(upper) else float(df["close"].iloc[-1]),
            "middle": float(mid) if not pd.isna(mid) else float(df["close"].iloc[-1]),
            "lower": float(lower) if not pd.isna(lower) else float(df["close"].iloc[-1]),
        }

    def _atr(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        result = ta.atr(df["high"], df["low"], df["close"], length=period)
        if result is None or result.empty:
            return {"value": 0.0}
        val = result.iloc[-1]
        return {"value": float(val) if not pd.isna(val) else 0.0}

    def _adx(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        result = ta.adx(df["high"], df["low"], df["close"], length=period)
        if result is None or result.empty:
            return {"adx": 0.0, "plus_di": 0.0, "minus_di": 0.0}
        adx_val = result.iloc[-1, 0]
        plus_di = result.iloc[-1, 1]
        minus_di = result.iloc[-1, 2]
        return {
            "adx": float(adx_val) if not pd.isna(adx_val) else 0.0,
            "plus_di": float(plus_di) if not pd.isna(plus_di) else 0.0,
            "minus_di": float(minus_di) if not pd.isna(minus_di) else 0.0,
        }

    def _cci(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        result = ta.cci(df["high"], df["low"], df["close"], length=period)
        if result is None or result.empty:
            return {"value": 0.0}
        val = result.iloc[-1]
        return {"value": float(val) if not pd.isna(val) else 0.0}

    def _williams_r(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        period = params.get("period", 14)
        result = ta.willr(df["high"], df["low"], df["close"], length=period)
        if result is None or result.empty:
            return {"value": -50.0}
        val = result.iloc[-1]
        return {"value": float(val) if not pd.isna(val) else -50.0}

    # --- Batch computation for charting ---

    @staticmethod
    def _series_to_list(series: pd.Series, n: int) -> list[float | None]:
        """Convert a pandas Series to a list[float|None] of length n."""
        out: list[float | None] = [None] * n
        if series is None:
            return out
        for i, val in enumerate(series):
            if i < n:
                out[i] = float(val) if not pd.isna(val) else None
        return out

    def _compute_full(self, name: str, params: dict) -> dict[str, list[float | None]]:
        """Compute a built-in indicator over the full DataFrame at once (O(n))."""
        df = self._df
        n = len(df)

        if name == "RSI":
            period = params.get("period", 14)
            r = ta.rsi(df["close"], length=period)
            return {"value": self._series_to_list(r, n)}

        if name == "EMA":
            period = params.get("period", 20)
            r = ta.ema(df["close"], length=period)
            return {"value": self._series_to_list(r, n)}

        if name == "SMA":
            period = params.get("period", 20)
            r = ta.sma(df["close"], length=period)
            return {"value": self._series_to_list(r, n)}

        if name == "MACD":
            fast = params.get("fast_ema", 12)
            slow = params.get("slow_ema", 26)
            sig = params.get("signal", 9)
            r = ta.macd(df["close"], fast=fast, slow=slow, signal=sig)
            if r is None or r.empty:
                return {"macd": [None] * n, "signal": [None] * n, "histogram": [None] * n}
            return {
                "macd": self._series_to_list(r.iloc[:, 0], n),
                "signal": self._series_to_list(r.iloc[:, 2], n),
                "histogram": self._series_to_list(r.iloc[:, 1], n),
            }

        if name == "Stochastic":
            k_period = params.get("k_period", 5)
            d_period = params.get("d_period", 3)
            slowing = params.get("slowing", 3)
            r = ta.stoch(df["high"], df["low"], df["close"], k=k_period, d=d_period, smooth_k=slowing)
            if r is None or r.empty:
                return {"k": [None] * n, "d": [None] * n}
            return {
                "k": self._series_to_list(r.iloc[:, 0], n),
                "d": self._series_to_list(r.iloc[:, 1], n),
            }

        if name == "Bollinger":
            period = params.get("period", 20)
            deviation = params.get("deviation", 2.0)
            r = ta.bbands(df["close"], length=period, std=deviation)
            if r is None or r.empty:
                return {"lower": [None] * n, "middle": [None] * n, "upper": [None] * n}
            return {
                "lower": self._series_to_list(r.iloc[:, 0], n),
                "middle": self._series_to_list(r.iloc[:, 1], n),
                "upper": self._series_to_list(r.iloc[:, 2], n),
            }

        if name == "ATR":
            period = params.get("period", 14)
            r = ta.atr(df["high"], df["low"], df["close"], length=period)
            return {"value": self._series_to_list(r, n)}

        if name == "ADX":
            period = params.get("period", 14)
            r = ta.adx(df["high"], df["low"], df["close"], length=period)
            if r is None or r.empty:
                return {"adx": [None] * n, "plus_di": [None] * n, "minus_di": [None] * n}
            return {
                "adx": self._series_to_list(r.iloc[:, 0], n),
                "plus_di": self._series_to_list(r.iloc[:, 1], n),
                "minus_di": self._series_to_list(r.iloc[:, 2], n),
            }

        if name == "CCI":
            period = params.get("period", 14)
            r = ta.cci(df["high"], df["low"], df["close"], length=period)
            return {"value": self._series_to_list(r, n)}

        if name == "WilliamsR":
            period = params.get("period", 14)
            r = ta.willr(df["high"], df["low"], df["close"], length=period)
            return {"value": self._series_to_list(r, n)}

        raise ValueError(f"No full computation for: {name}")

    def compute_series(self, name: str, params: dict) -> dict[str, list[float | None]]:
        """Compute indicator over the full bar array.

        For built-in indicators, uses _compute_full() (single pandas_ta call).
        For custom indicators, falls back to iterating compute_at() per bar.
        Returns dict of output_name → list[float|None], same length as bars.
        """
        n = len(self._df)
        if n == 0:
            return {"value": []}

        # Try built-in full computation first
        builtin_names = {"RSI", "EMA", "SMA", "MACD", "Stochastic", "Bollinger", "ATR", "ADX", "CCI", "WilliamsR"}
        if name in builtin_names:
            try:
                return self._compute_full(name, params)
            except Exception as e:
                logger.warning(f"Full computation failed for {name}: {e}")

        # Fallback: iterate bar-by-bar (custom indicators or if full failed)
        results: dict[str, list[float | None]] = {}
        for i in range(n):
            vals = self.compute_at(i, name, params)
            if not results:
                results = {k: [] for k in vals}
            for k, v in vals.items():
                val = float(v) if v != EMPTY_VALUE and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else None
                results[k].append(val)
        return results

    # --- Custom Indicators ---

    def _smc_structure(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        """Smart Money Concepts — Market Structure.

        Swing detection (lookback N bars for local high/low), ATR filtering,
        trend via HH/HL vs LH/LL, OTE zone = 61.8%-78.6% Fibonacci retracement.
        """
        swing_length = params.get("swing_length", 10)
        atr_length = params.get("atr_length", 14)
        atr_mult = params.get("atr_multiplier", 0.5)

        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        n = len(df)

        if n < swing_length * 2 + 1:
            return self._empty_result("SMC_Structure")

        # Compute ATR for filtering
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=atr_length)
        current_atr = float(atr_series.iloc[-1]) if atr_series is not None and not atr_series.empty and not pd.isna(atr_series.iloc[-1]) else 1.0
        min_swing_size = current_atr * atr_mult

        # Find swing highs and lows
        swing_highs = []  # (index, price)
        swing_lows = []

        for i in range(swing_length, n - 1):  # don't look at last bar (not confirmed)
            # Swing high: highest in window
            window_high = highs[max(0, i - swing_length):i + swing_length + 1]
            if highs[i] == np.max(window_high) and highs[i] - lows[i] >= min_swing_size * 0.3:
                swing_highs.append((i, float(highs[i])))

            # Swing low: lowest in window
            window_low = lows[max(0, i - swing_length):i + swing_length + 1]
            if lows[i] == np.min(window_low) and highs[i] - lows[i] >= min_swing_size * 0.3:
                swing_lows.append((i, float(lows[i])))

        # Determine trend from recent swings
        trend = 0.0
        ref_high = 0.0
        ref_low = 0.0
        strong_high = 0.0
        strong_low = 0.0

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            sh1_price = swing_highs[-2][1]
            sh2_price = swing_highs[-1][1]
            sl1_price = swing_lows[-2][1]
            sl2_price = swing_lows[-1][1]

            # Bullish: Higher Highs + Higher Lows
            if sh2_price > sh1_price and sl2_price > sl1_price:
                trend = 1.0
            # Bearish: Lower Highs + Lower Lows
            elif sh2_price < sh1_price and sl2_price < sl1_price:
                trend = -1.0

            ref_high = sh2_price
            ref_low = sl2_price

            # Strong levels (unbroken)
            if trend == 1.0:
                strong_low = sl2_price
                strong_high = sh2_price
            elif trend == -1.0:
                strong_high = sh2_price
                strong_low = sl2_price
            else:
                strong_high = max(sh1_price, sh2_price)
                strong_low = min(sl1_price, sl2_price)

        # Equilibrium and OTE
        equilibrium = (ref_high + ref_low) / 2.0 if ref_high and ref_low else 0.0
        rng = ref_high - ref_low
        if trend == 1.0 and rng > 0:
            # Bullish OTE: 61.8%-78.6% retracement from high
            ote_top = ref_high - rng * 0.618
            ote_bottom = ref_high - rng * 0.786
        elif trend == -1.0 and rng > 0:
            # Bearish OTE: 61.8%-78.6% retracement from low
            ote_bottom = ref_low + rng * 0.618
            ote_top = ref_low + rng * 0.786
        else:
            ote_top = 0.0
            ote_bottom = 0.0

        # Current bar swing values
        last_sh = swing_highs[-1] if swing_highs else None
        last_sl = swing_lows[-1] if swing_lows else None

        return {
            "trend": trend,
            "swing_high": last_sh[1] if last_sh else EMPTY_VALUE,
            "swing_low": last_sl[1] if last_sl else EMPTY_VALUE,
            "strong_low": strong_low,
            "strong_high": strong_high,
            "ref_high": ref_high,
            "ref_low": ref_low,
            "equilibrium": equilibrium,
            "ote_top": ote_top,
            "ote_bottom": ote_bottom,
            "swing_high_clr": 1.0 if last_sh and closes[-1] > last_sh[1] else 0.0,
            "swing_low_clr": 1.0 if last_sl and closes[-1] < last_sl[1] else 0.0,
        }

    def _ob_fvg(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        """Order Blocks & Fair Value Gaps.

        3-layer ZigZag, order block detection, FVG (3-candle imbalance), confluence.
        """
        zz_depths = params.get("zz_depths", [5, 13, 34])
        ob_lookback = params.get("ob_lookback", 20)
        ob_strength = params.get("ob_strength", 3)
        fvg_min_atr = params.get("fvg_min_size", 0.5)

        highs = df["high"].values
        lows = df["low"].values
        opens = df["open"].values
        closes = df["close"].values
        n = len(df)

        if n < max(zz_depths) * 2 + 5:
            return self._empty_result("OB_FVG")

        # ATR for sizing
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
        current_atr = float(atr_series.iloc[-1]) if atr_series is not None and not atr_series.empty and not pd.isna(atr_series.iloc[-1]) else 1.0

        # ZigZag layers
        zz_results = {}
        for layer_idx, depth in enumerate(zz_depths[:3], 1):
            zz_up = EMPTY_VALUE
            zz_down = EMPTY_VALUE
            for i in range(depth, n - 1):
                win_high = highs[max(0, i - depth):i + depth + 1]
                if highs[i] == np.max(win_high):
                    zz_up = float(highs[i])
                win_low = lows[max(0, i - depth):i + depth + 1]
                if lows[i] == np.min(win_low):
                    zz_down = float(lows[i])
            zz_results[f"zz{layer_idx}_up"] = zz_up
            zz_results[f"zz{layer_idx}_down"] = zz_down

        # Order block detection — look for impulsive candle before big move
        ob_upper = 0.0
        ob_lower = 0.0
        ob_type = 0.0
        ob_time = 0.0

        lookback_start = max(0, n - ob_lookback)
        for i in range(n - 2, lookback_start, -1):
            body = abs(closes[i] - opens[i])
            if body < current_atr * 0.3:
                continue

            # Check for impulsive move after this candle
            if i + 1 < n:
                next_body = abs(closes[i + 1] - opens[i + 1])
                if next_body < current_atr * 0.5:
                    continue

                # Bullish OB: bearish candle followed by strong bullish
                if closes[i] < opens[i] and closes[i + 1] > opens[i + 1] and next_body > body * 1.5:
                    ob_lower = float(lows[i])
                    ob_upper = float(highs[i])
                    ob_type = 1.0
                    ob_time = float(i)
                    break

                # Bearish OB: bullish candle followed by strong bearish
                if closes[i] > opens[i] and closes[i + 1] < opens[i + 1] and next_body > body * 1.5:
                    ob_lower = float(lows[i])
                    ob_upper = float(highs[i])
                    ob_type = -1.0
                    ob_time = float(i)
                    break

        # Fair Value Gap detection — 3-candle imbalance
        fvg_upper = 0.0
        fvg_lower = 0.0
        fvg_type = 0.0
        fvg_filled = 0.0
        fvg_reversed = 0.0

        for i in range(n - 3, max(0, n - 50), -1):
            # Bullish FVG: candle[i+2].low > candle[i].high (gap up)
            if lows[i + 2] > highs[i]:
                gap_size = lows[i + 2] - highs[i]
                if gap_size >= current_atr * fvg_min_atr:
                    fvg_lower = float(highs[i])
                    fvg_upper = float(lows[i + 2])
                    fvg_type = 1.0
                    # Check if filled
                    for j in range(i + 3, n):
                        if lows[j] <= fvg_lower:
                            fvg_filled = 1.0
                            break
                    break

            # Bearish FVG: candle[i+2].high < candle[i].low (gap down)
            if highs[i + 2] < lows[i]:
                gap_size = lows[i] - highs[i + 2]
                if gap_size >= current_atr * fvg_min_atr:
                    fvg_upper = float(lows[i])
                    fvg_lower = float(highs[i + 2])
                    fvg_type = -1.0
                    for j in range(i + 3, n):
                        if highs[j] >= fvg_upper:
                            fvg_filled = 1.0
                            break
                    break

        # Confluence — overlap between OB and FVG
        overlap_upper = 0.0
        overlap_lower = 0.0
        if ob_upper > 0 and fvg_upper > 0:
            ol = max(ob_lower, fvg_lower)
            oh = min(ob_upper, fvg_upper)
            if oh > ol:
                overlap_upper = oh
                overlap_lower = ol

        # Combined signals
        combined_all = 0.0
        combined_partial = 0.0
        zz_vals = [v for k, v in zz_results.items() if v != EMPTY_VALUE and v != 0.0]
        price = float(closes[-1])

        # Check if multiple ZZ layers point to same zone (within ATR)
        if len(zz_vals) >= 2:
            for z in zz_vals:
                nearby = sum(1 for z2 in zz_vals if abs(z - z2) < current_atr)
                if nearby >= 3:
                    combined_all = z
                elif nearby >= 2:
                    combined_partial = z

        result = {
            **zz_results,
            "combined_all": combined_all,
            "combined_partial": combined_partial,
            "ob_upper": ob_upper,
            "ob_lower": ob_lower,
            "overlap_upper": overlap_upper,
            "overlap_lower": overlap_lower,
            "ob_type": ob_type,
            "ob_time": ob_time,
            "hline_upper": ob_upper if ob_upper > 0 else fvg_upper,
            "hline_lower": ob_lower if ob_lower > 0 else fvg_lower,
            "fvg_upper": fvg_upper,
            "fvg_lower": fvg_lower,
            "fvg_filled": fvg_filled,
            "fvg_type": fvg_type,
            "fvg_reversed": fvg_reversed,
        }
        return result

    def _nw_envelope(self, df: pd.DataFrame, params: dict) -> dict[str, float]:
        """Nadaraya-Watson kernel regression with ATR-based envelope bands."""
        bandwidth = params.get("bandwidth", params.get("relative_weighting", 8.0))
        lookback = params.get("lookback", params.get("lookback_window", 200))
        atr_length = params.get("atr_length", 14)
        near_mult = params.get("near_mult", params.get("nearFactor", 1.0))
        far_mult = params.get("far_mult", params.get("farFactor", 2.7))
        avg_mult = (near_mult + far_mult) / 2.0

        closes = df["close"].values
        n = len(df)

        if n < max(atr_length + 1, 10):
            return self._empty_result("NW_Envelope")

        # ATR for band width
        atr_series = ta.atr(df["high"], df["low"], df["close"], length=atr_length)
        current_atr = float(atr_series.iloc[-1]) if atr_series is not None and not atr_series.empty and not pd.isna(atr_series.iloc[-1]) else 1.0

        # Nadaraya-Watson kernel regression at last bar
        # kernel(x) = exp(-0.5 * ((x - xi) / h)^2)
        end_idx = n - 1
        start_idx = max(0, end_idx - lookback)
        window = closes[start_idx:end_idx + 1]
        wn = len(window)

        if wn < 3:
            return self._empty_result("NW_Envelope")

        # Compute NW estimate at the last two points for direction
        def nw_estimate(target_idx: int) -> float:
            weights = np.zeros(wn)
            for j in range(wn):
                dist = (target_idx - j) / bandwidth
                weights[j] = math.exp(-0.5 * dist * dist)
            total_w = np.sum(weights)
            if total_w == 0:
                return float(window[-1])
            return float(np.dot(weights, window) / total_w)

        nw_current = nw_estimate(wn - 1)
        nw_prev = nw_estimate(wn - 2) if wn >= 3 else nw_current

        nw_bullish = 1.0 if nw_current > nw_prev else 0.0
        nw_bearish = 1.0 if nw_current < nw_prev else 0.0

        upper_far = nw_current + current_atr * far_mult
        upper_avg = nw_current + current_atr * avg_mult
        upper_near = nw_current + current_atr * near_mult
        lower_near = nw_current - current_atr * near_mult
        lower_avg = nw_current - current_atr * avg_mult
        lower_far = nw_current - current_atr * far_mult

        return {
            "nw_bullish": nw_bullish,
            "nw_bearish": nw_bearish,
            "upper_far": upper_far,
            "upper_avg": upper_avg,
            "upper_near": upper_near,
            "lower_near": lower_near,
            "lower_avg": lower_avg,
            "lower_far": lower_far,
        }
