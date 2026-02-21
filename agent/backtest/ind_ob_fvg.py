"""OB FVG Indicator — faithful PineScript conversion.

Detects institutional supply/demand zones via price gaps (FVGs) and liquidity
sweeps. Tracks Order Blocks through lifecycle: active → tested → breaker → reversed.

Based on PineScript "OB FVG Indicator" (v6).

Key detection logic:
- Bullish OB: gap up (high[idx] < low[0]) with low sweep (low[idx] < low[idx-1] and < low[idx+1])
- Bearish OB: gap down (low[idx] > high[0]) with high sweep (high[idx] > high[idx-1] and > high[idx+1])
- FVG: gap between OB candle and the validation candle (bar[0])
- OB states: active → tested (price reaches test%) → breaker (close breaks OB) → reversed (close reverses breaker)
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta


@dataclass
class OBState:
    """Tracks one Order Block through its lifecycle."""
    bar_index: int          # Bar where OB was identified
    gap_bar: int            # Gap validation bar (bar[0] at detection time)
    high: float             # OB candle high
    low: float              # OB candle low
    is_long: bool           # True for bullish, False for bearish
    is_set2: bool           # True if detected at bar[3] (vs bar[2])
    state: str = "active"   # "active", "tested", "breaker", "reversed"
    is_tested: bool = False
    has_reached_test_level: bool = False
    gap_level: float = 0.0  # Validation bar's low (bullish) or high (bearish) for FVG
    is_fvg_filled: bool = False
    breaker_bar: int = 0
    reversal_bar: int = 0


# ─── Default outputs ──────────────────────────────────────────────────

OB_FVG_EMPTY: dict[str, float] = {
    "ob_upper": 0.0,
    "ob_lower": 0.0,
    "ob_type": 0.0,       # +1 bullish, -1 bearish, 0 none
    "ob_state": 0.0,      # 1=active, 2=tested, 3=breaker, 4=reversed
    "fvg_upper": 0.0,
    "fvg_lower": 0.0,
    "fvg_filled": 0.0,
    "bull_ob_count": 0.0,
    "bear_ob_count": 0.0,
    "bull_breaker_count": 0.0,
    "bear_breaker_count": 0.0,
}

_STATE_MAP = {"active": 1.0, "tested": 2.0, "breaker": 3.0, "reversed": 4.0}


# ─── Detection functions (match PineScript exactly) ──────────────────

def _is_bearish_ob(highs: np.ndarray, lows: np.ndarray, i: int, idx: int) -> tuple[bool, bool]:
    """Check bearish OB conditions.

    PineScript: isBearishOB(idx)
    - hasGap = low[idx] > high[0] and low[idx] > low[0]
    - idx==2: high[2] > high[1] and high[2] > high[3]
    - idx==3: high[3] > high[2] and high[3] > high[4]

    In Python, bar[0] = bar at index i, bar[k] = bar at index i-k
    """
    n = len(highs)
    # Need enough bars looking back
    if i - idx < 0 or (idx == 2 and i - 3 < 0) or (idx == 3 and i - 4 < 0):
        return False, False

    # Gap validation: low of OB candle > high and low of current bar
    has_gap = lows[i - idx] > highs[i] and lows[i - idx] > lows[i]

    is_valid = False
    is_bar3 = False

    if has_gap:
        if idx == 2:
            # Bar[2] sweep: high[2] > high[1] and high[2] > high[3]
            if highs[i - 2] > highs[i - 1] and highs[i - 2] > highs[i - 3]:
                is_valid = True
        elif idx == 3:
            # Bar[3] sweep: high[3] > high[2] and high[3] > high[4]
            if highs[i - 3] > highs[i - 2] and highs[i - 3] > highs[i - 4]:
                is_valid = True
                is_bar3 = True

    return is_valid, is_bar3


def _is_bullish_ob(highs: np.ndarray, lows: np.ndarray, i: int, idx: int) -> tuple[bool, bool]:
    """Check bullish OB conditions.

    PineScript: isBullishOB(idx)
    - hasGap = high[idx] < low[0] and high[idx] < high[0]
    - idx==2: low[2] < low[1] and low[2] < low[3]
    - idx==3: low[3] < low[2] and low[3] < low[4]
    """
    n = len(highs)
    if i - idx < 0 or (idx == 2 and i - 3 < 0) or (idx == 3 and i - 4 < 0):
        return False, False

    has_gap = highs[i - idx] < lows[i] and highs[i - idx] < highs[i]

    is_valid = False
    is_bar3 = False

    if has_gap:
        if idx == 2:
            if lows[i - 2] < lows[i - 1] and lows[i - 2] < lows[i - 3]:
                is_valid = True
        elif idx == 3:
            if lows[i - 3] < lows[i - 2] and lows[i - 3] < lows[i - 4]:
                is_valid = True
                is_bar3 = True

    return is_valid, is_bar3


# ─── State update functions ──────────────────────────────────────────

def _update_ob_states(obs: list[OBState], i: int,
                      close: float, low: float, high: float,
                      test_percent: float, fill_percent: float) -> None:
    """Update all OB states on the current bar (matching PineScript updateOBStates)."""
    for ob in obs:
        if ob.state == "reversed":
            continue

        bars_since_gap = i - ob.gap_bar
        if bars_since_gap < 1:
            continue

        # Check breaker condition
        if ob.state in ("active", "tested"):
            if ob.is_long:  # Bullish OB → breaker when close < OB low
                if close < ob.low:
                    ob.state = "breaker"
                    ob.breaker_bar = i
            else:  # Bearish OB → breaker when close > OB high
                if close > ob.high:
                    ob.state = "breaker"
                    ob.breaker_bar = i

        # Check reversal condition
        elif ob.state == "breaker":
            if ob.is_long:  # Breaker resistance → reversed when close > OB high
                if close > ob.high:
                    ob.state = "reversed"
                    ob.reversal_bar = i
            else:  # Breaker support → reversed when close < OB low
                if close < ob.low:
                    ob.state = "reversed"
                    ob.reversal_bar = i

        # Check test condition (two-step MQL5-style)
        if not ob.is_tested and ob.state == "active":
            ob_range = ob.high - ob.low
            test_distance = ob_range * test_percent / 100.0

            if ob.is_long:
                test_price = ob.high - test_distance
                # Step 1: price reaches test level
                if not ob.has_reached_test_level and low <= test_price:
                    ob.has_reached_test_level = True
                # Step 2: price returns toward OB
                if ob.has_reached_test_level and (low >= ob.low or (low < ob.low and high >= ob.low)):
                    ob.is_tested = True
            else:
                test_price = ob.low + test_distance
                if not ob.has_reached_test_level and high >= test_price:
                    ob.has_reached_test_level = True
                if ob.has_reached_test_level and (high <= ob.high or (high > ob.high and low <= ob.high)):
                    ob.is_tested = True

        # Check FVG fill
        if not ob.is_fvg_filled:
            fvg_height = abs(ob.gap_level - (ob.high if ob.is_long else ob.low))
            if fvg_height > 0:
                if ob.is_long:
                    fill_level = ob.gap_level - (fvg_height * fill_percent / 100.0)
                    # PineScript uses low[1], but we use current bar's low for compute_series
                    if low <= fill_level:
                        ob.is_fvg_filled = True
                else:
                    fill_level = ob.gap_level + (fvg_height * fill_percent / 100.0)
                    if high >= fill_level:
                        ob.is_fvg_filled = True


def _cleanup_obs(obs: list[OBState], max_obs: int, bars_keep_reversed: int,
                 current_bar: int) -> list[OBState]:
    """Remove old reversed OBs and enforce max count."""
    if len(obs) <= int(max_obs * 0.8):
        return obs

    # Remove old reversed OBs
    obs = [ob for ob in obs
           if not (ob.state == "reversed" and (current_bar - ob.reversal_bar) > bars_keep_reversed)]

    # If still too many, remove oldest
    while len(obs) > max_obs:
        obs.pop(0)

    return obs


# ═══════════════════════════════════════════════════════════════════════
# compute_at — bar-by-bar for strategy engine
# ═══════════════════════════════════════════════════════════════════════

def ob_fvg_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute OB FVG indicator at the last bar of the slice."""
    max_obs = params.get("max_obs", 500)
    bars_keep_reversed = params.get("bars_keep_reversed", 50)
    test_percent = params.get("test_percent", 30.0)
    fill_percent = params.get("fill_percent", 50.0)

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    if n < 5:
        return dict(OB_FVG_EMPTY)

    # Run full simulation up to last bar
    all_obs: list[OBState] = []
    prev_bull2 = False
    prev_bull3 = False
    prev_bear2 = False
    prev_bear3 = False
    bull_count = 0
    bear_count = 0

    for i in range(4, n):
        # Detect OBs
        bull2_valid, _ = _is_bullish_ob(highs, lows, i, 2)
        bull3_valid, _ = _is_bullish_ob(highs, lows, i, 3)
        bear2_valid, _ = _is_bearish_ob(highs, lows, i, 2)
        bear3_valid, _ = _is_bearish_ob(highs, lows, i, 3)

        # Add newly detected (edge trigger)
        if bull2_valid and not prev_bull2:
            ob = OBState(bar_index=i - 2, gap_bar=i, high=float(highs[i - 2]),
                         low=float(lows[i - 2]), is_long=True, is_set2=False,
                         gap_level=float(lows[i]))
            all_obs.append(ob)
            bull_count += 1

        if bull3_valid and not prev_bull3:
            ob = OBState(bar_index=i - 3, gap_bar=i, high=float(highs[i - 3]),
                         low=float(lows[i - 3]), is_long=True, is_set2=True,
                         gap_level=float(lows[i]))
            all_obs.append(ob)
            bull_count += 1

        if bear2_valid and not prev_bear2:
            ob = OBState(bar_index=i - 2, gap_bar=i, high=float(highs[i - 2]),
                         low=float(lows[i - 2]), is_long=False, is_set2=False,
                         gap_level=float(highs[i]))
            all_obs.append(ob)
            bear_count += 1

        if bear3_valid and not prev_bear3:
            ob = OBState(bar_index=i - 3, gap_bar=i, high=float(highs[i - 3]),
                         low=float(lows[i - 3]), is_long=False, is_set2=True,
                         gap_level=float(highs[i]))
            all_obs.append(ob)
            bear_count += 1

        prev_bull2 = bull2_valid
        prev_bull3 = bull3_valid
        prev_bear2 = bear2_valid
        prev_bear3 = bear3_valid

        # Update states
        _update_ob_states(all_obs, i, float(closes[i]), float(lows[i]),
                          float(highs[i]), test_percent, fill_percent)

        # Cleanup
        all_obs = _cleanup_obs(all_obs, max_obs, bars_keep_reversed, i)

    # Find nearest active/tested OB to current price
    last_close = float(closes[-1])
    best_ob = None
    best_dist = float("inf")

    for ob in all_obs:
        if ob.state in ("active", "tested", "breaker"):
            mid = (ob.high + ob.low) / 2.0
            dist = abs(mid - last_close)
            if dist < best_dist:
                best_dist = dist
                best_ob = ob

    # Find nearest active FVG
    best_fvg_upper = 0.0
    best_fvg_lower = 0.0
    fvg_filled = 0.0
    best_fvg_dist = float("inf")

    for ob in all_obs:
        if not ob.is_fvg_filled:
            if ob.is_long:
                fvg_top = ob.gap_level
                fvg_bot = ob.high
            else:
                fvg_top = ob.low
                fvg_bot = ob.gap_level
            mid = (fvg_top + fvg_bot) / 2.0
            dist = abs(mid - last_close)
            if dist < best_fvg_dist:
                best_fvg_dist = dist
                best_fvg_upper = fvg_top
                best_fvg_lower = fvg_bot
                fvg_filled = 0.0

    # Count breakers
    bull_breakers = sum(1 for ob in all_obs if ob.state == "breaker" and ob.is_long)
    bear_breakers = sum(1 for ob in all_obs if ob.state == "breaker" and not ob.is_long)

    return {
        "ob_upper": best_ob.high if best_ob else 0.0,
        "ob_lower": best_ob.low if best_ob else 0.0,
        "ob_type": (1.0 if best_ob.is_long else -1.0) if best_ob else 0.0,
        "ob_state": _STATE_MAP.get(best_ob.state, 0.0) if best_ob else 0.0,
        "fvg_upper": best_fvg_upper,
        "fvg_lower": best_fvg_lower,
        "fvg_filled": fvg_filled,
        "bull_ob_count": float(bull_count),
        "bear_ob_count": float(bear_count),
        "bull_breaker_count": float(bull_breakers),
        "bear_breaker_count": float(bear_breakers),
    }


# ═══════════════════════════════════════════════════════════════════════
# compute_series — full array for charting
# ═══════════════════════════════════════════════════════════════════════

def ob_fvg_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute OB FVG over all bars for chart overlay."""
    max_obs = params.get("max_obs", 500)
    bars_keep_reversed = params.get("bars_keep_reversed", 50)
    test_percent = params.get("test_percent", 30.0)
    fill_percent = params.get("fill_percent", 50.0)

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    out_ob_upper: list[float | None] = [None] * n
    out_ob_lower: list[float | None] = [None] * n
    out_ob_type: list[float | None] = [None] * n
    out_ob_state: list[float | None] = [None] * n
    out_fvg_upper: list[float | None] = [None] * n
    out_fvg_lower: list[float | None] = [None] * n

    if n < 5:
        return {
            "ob_upper": out_ob_upper, "ob_lower": out_ob_lower,
            "ob_type": out_ob_type, "ob_state": out_ob_state,
            "fvg_upper": out_fvg_upper, "fvg_lower": out_fvg_lower,
        }

    all_obs: list[OBState] = []
    prev_bull2 = False
    prev_bull3 = False
    prev_bear2 = False
    prev_bear3 = False

    for i in range(4, n):
        # Detect OBs
        bull2_valid, _ = _is_bullish_ob(highs, lows, i, 2)
        bull3_valid, _ = _is_bullish_ob(highs, lows, i, 3)
        bear2_valid, _ = _is_bearish_ob(highs, lows, i, 2)
        bear3_valid, _ = _is_bearish_ob(highs, lows, i, 3)

        if bull2_valid and not prev_bull2:
            all_obs.append(OBState(
                bar_index=i - 2, gap_bar=i, high=float(highs[i - 2]),
                low=float(lows[i - 2]), is_long=True, is_set2=False,
                gap_level=float(lows[i]),
            ))

        if bull3_valid and not prev_bull3:
            all_obs.append(OBState(
                bar_index=i - 3, gap_bar=i, high=float(highs[i - 3]),
                low=float(lows[i - 3]), is_long=True, is_set2=True,
                gap_level=float(lows[i]),
            ))

        if bear2_valid and not prev_bear2:
            all_obs.append(OBState(
                bar_index=i - 2, gap_bar=i, high=float(highs[i - 2]),
                low=float(lows[i - 2]), is_long=False, is_set2=False,
                gap_level=float(highs[i]),
            ))

        if bear3_valid and not prev_bear3:
            all_obs.append(OBState(
                bar_index=i - 3, gap_bar=i, high=float(highs[i - 3]),
                low=float(lows[i - 3]), is_long=False, is_set2=True,
                gap_level=float(highs[i]),
            ))

        prev_bull2 = bull2_valid
        prev_bull3 = bull3_valid
        prev_bear2 = bear2_valid
        prev_bear3 = bear3_valid

        # Update states
        _update_ob_states(all_obs, i, float(closes[i]), float(lows[i]),
                          float(highs[i]), test_percent, fill_percent)
        all_obs = _cleanup_obs(all_obs, max_obs, bars_keep_reversed, i)

        # Output: nearest active OB and unfilled FVG to current price
        cur_close = float(closes[i])

        # Nearest active OB
        best_ob = None
        best_dist = float("inf")
        for ob in all_obs:
            if ob.state in ("active", "tested", "breaker"):
                mid = (ob.high + ob.low) / 2.0
                dist = abs(mid - cur_close)
                if dist < best_dist:
                    best_dist = dist
                    best_ob = ob

        if best_ob:
            out_ob_upper[i] = best_ob.high
            out_ob_lower[i] = best_ob.low
            out_ob_type[i] = 1.0 if best_ob.is_long else -1.0
            out_ob_state[i] = _STATE_MAP.get(best_ob.state, 0.0)

        # Nearest unfilled FVG
        best_fvg = None
        best_fvg_dist = float("inf")
        for ob in all_obs:
            if not ob.is_fvg_filled:
                if ob.is_long:
                    fvg_top = ob.gap_level
                    fvg_bot = ob.high
                else:
                    fvg_top = ob.low
                    fvg_bot = ob.gap_level
                mid = (fvg_top + fvg_bot) / 2.0
                dist = abs(mid - cur_close)
                if dist < best_fvg_dist:
                    best_fvg_dist = dist
                    best_fvg = ob

        if best_fvg:
            if best_fvg.is_long:
                out_fvg_upper[i] = best_fvg.gap_level
                out_fvg_lower[i] = best_fvg.high
            else:
                out_fvg_upper[i] = best_fvg.low
                out_fvg_lower[i] = best_fvg.gap_level

    return {
        "ob_upper": out_ob_upper,
        "ob_lower": out_ob_lower,
        "ob_type": out_ob_type,
        "ob_state": out_ob_state,
        "fvg_upper": out_fvg_upper,
        "fvg_lower": out_fvg_lower,
    }
