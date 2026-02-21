"""Python indicator engine for backtesting.

Computes 10 standard indicators (via pandas_ta) and 4 custom indicators
(faithfully converted from PineScript) from raw OHLCV bars.
All computations use only past data (no look-ahead).
"""

import bisect
import math
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta
from loguru import logger

from agent.backtest.ind_nw import (
    ENVELOPE_EMPTY, KERNEL_EMPTY,
    nw_envelope_at, nw_envelope_series,
    nw_rq_kernel_at, nw_rq_kernel_series,
)
from agent.backtest.ind_ob_fvg import OB_FVG_EMPTY, ob_fvg_at, ob_fvg_series
from agent.backtest.ind_smc import SMC_EMPTY, smc_structure_at, smc_structure_series
from agent.backtest.ind_tpo import TPO_EMPTY, tpo_at, tpo_series
from agent.indicators.custom import discover_custom_indicators
from agent.models.market import Bar

EMPTY_VALUE = 1e308  # sentinel for "no value"


OVERLAY_INDICATORS = {"EMA", "SMA", "Bollinger", "NW_Envelope", "NW_RQ_Kernel", "KeltnerChannel", "SMC_Structure", "OB_FVG", "TPO"}
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
        # PineScript-converted indicators (external modules)
        if name == "SMC_Structure":
            return smc_structure_at(df, params)
        if name == "OB_FVG":
            return ob_fvg_at(df, params)
        if name == "NW_Envelope":
            return nw_envelope_at(df, params)
        if name == "NW_RQ_Kernel":
            return nw_rq_kernel_at(df, params)
        if name == "TPO":
            return tpo_at(df, params)

        # Standard indicators (pandas_ta)
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
            "SMC_Structure": dict(SMC_EMPTY),
            "OB_FVG": dict(OB_FVG_EMPTY),
            "NW_Envelope": dict(ENVELOPE_EMPTY),
            "NW_RQ_Kernel": dict(KERNEL_EMPTY),
            "TPO": dict(TPO_EMPTY),
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

    # Old _compute_full_smc and _compute_full_ob_fvg removed — replaced by ind_smc.py and ind_ob_fvg.py

    def compute_series(self, name: str, params: dict) -> dict[str, list[float | None]]:
        """Compute indicator over the full bar array.

        For PineScript-converted indicators, uses dedicated module functions.
        For built-in indicators, uses _compute_full() (single pandas_ta call).
        For custom indicators, falls back to iterating compute_at() per bar.
        Returns dict of output_name → list[float|None], same length as bars.
        """
        n = len(self._df)
        if n == 0:
            return {"value": []}

        # PineScript-converted indicators (dedicated modules)
        if name == "SMC_Structure":
            try:
                return smc_structure_series(self._df, params)
            except Exception as e:
                logger.warning(f"SMC_Structure series computation failed: {e}")

        if name == "OB_FVG":
            try:
                return ob_fvg_series(self._df, params)
            except Exception as e:
                logger.warning(f"OB_FVG series computation failed: {e}")

        if name == "NW_Envelope":
            try:
                return nw_envelope_series(self._df, params)
            except Exception as e:
                logger.warning(f"NW_Envelope series computation failed: {e}")

        if name == "NW_RQ_Kernel":
            try:
                return nw_rq_kernel_series(self._df, params)
            except Exception as e:
                logger.warning(f"NW_RQ_Kernel series computation failed: {e}")

        if name == "TPO":
            try:
                return tpo_series(self._df, params)
            except Exception as e:
                logger.warning(f"TPO series computation failed: {e}")

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

    # Old _smc_structure, _ob_fvg, _nw_envelope removed — replaced by ind_smc.py, ind_ob_fvg.py, ind_nw.py


# --- Multi-Timeframe Precomputed Engine ---

_TF_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}


def _tf_to_minutes(tf: str) -> int:
    """Convert timeframe string to minutes."""
    m = _TF_MINUTES.get(tf.upper())
    if m is None:
        raise ValueError(f"Unknown timeframe: {tf}")
    return m


class MultiTFIndicatorEngine:
    """Wraps multiple IndicatorEngine instances (one per timeframe).

    Pre-computes all indicator series upfront via compute_series() for O(n)
    total work, then provides O(1) lookups by indicator_id + bar_index.
    Cross-timeframe alignment uses bisect (O(log n)) with no look-ahead.
    """

    def __init__(self):
        self._engines: dict[str, IndicatorEngine] = {}
        self._bars: dict[str, list[Bar]] = {}
        self._timestamps: dict[str, list[float]] = {}
        self._series: dict[str, dict[str, list[float]]] = {}

    def add_timeframe(self, tf: str, bars: list[Bar]) -> None:
        """Register bars for a timeframe."""
        tf = tf.upper()
        self._engines[tf] = IndicatorEngine(bars)
        self._bars[tf] = bars
        self._timestamps[tf] = [b.time.timestamp() for b in bars]

    def precompute(self, indicators: list) -> None:
        """Run compute_series() once per indicator (O(n) total).

        Filters out _markers keys and converts None → 0.0 to match
        existing compute_at() behaviour for warmup/missing values.
        """
        for ind_cfg in indicators:
            tf = ind_cfg.timeframe.upper() if ind_cfg.timeframe else next(iter(self._engines))
            engine = self._engines.get(tf)
            if engine is None:
                logger.warning(f"No bars for timeframe {tf}, skipping indicator {ind_cfg.id}")
                continue

            try:
                raw = engine.compute_series(ind_cfg.name, ind_cfg.params)
            except Exception as e:
                logger.warning(f"compute_series failed for {ind_cfg.id} ({ind_cfg.name}): {e}")
                raw = {}

            # Filter _markers keys and convert None → 0.0
            cleaned: dict[str, list[float]] = {}
            for key, values in raw.items():
                if key.startswith("_"):
                    continue
                cleaned[key] = [
                    0.0 if v is None else float(v)
                    for v in values
                ]
            self._series[ind_cfg.id] = cleaned

    def get_at(
        self,
        ind_id: str,
        primary_bar_idx: int,
        primary_tf: str,
        indicator_tf: str | None,
    ) -> dict[str, float]:
        """O(1) lookup for same-TF, O(log n) for cross-TF (via bisect).

        No look-ahead: uses bisect_right(timestamps, primary_ts) - 1 to
        find the last indicator bar whose open time <= primary bar's open time.
        """
        series = self._series.get(ind_id)
        if series is None:
            return {"value": 0.0}

        primary_tf = primary_tf.upper()
        ind_tf = (indicator_tf or primary_tf).upper()

        if ind_tf == primary_tf:
            # Same timeframe — direct index
            bar_idx = primary_bar_idx
        else:
            # Cross-TF alignment: find the most recent indicator bar
            primary_ts = self._timestamps[primary_tf][primary_bar_idx]
            ind_timestamps = self._timestamps.get(ind_tf)
            if ind_timestamps is None:
                return {"value": 0.0}
            bar_idx = bisect.bisect_right(ind_timestamps, primary_ts) - 1
            if bar_idx < 0:
                return {k: 0.0 for k in series}

        result: dict[str, float] = {}
        for key, values in series.items():
            if bar_idx < len(values):
                result[key] = values[bar_idx]
            else:
                result[key] = 0.0
        return result
