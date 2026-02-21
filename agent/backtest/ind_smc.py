"""SMC Structure Indicator — faithful PineScript conversion.

Smart Money Concepts market structure analysis:
- Swing detection (pivothigh/pivotlow) with alternation rule
- Trend classification: HH/HL (bullish), LH/LL (bearish), iH/iL (internal)
- BOS (Break of Structure) — trend continuation
- CHoCH (Change of Character) — trend reversal
- Strong High/Low levels (CHOCH trigger lines)
- Premium/Discount/OTE zones
- Equal Highs/Lows (liquidity pools) + sweep detection

Based on PineScript "SMC Structure" v1.13 (1670 lines).
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# ─── Constants ────────────────────────────────────────────────────────

SWING_HIGH = 1
SWING_LOW = -1
CLS_UNCLASSIFIED = 0
CLS_MAJOR = 1
CLS_INTERNAL = -1
TREND_BULLISH = 1
TREND_BEARISH = -1
TREND_UNDEFINED = 0


# ─── Data structures ─────────────────────────────────────────────────

@dataclass
class SwingPoint:
    swing_type: int       # SWING_HIGH or SWING_LOW
    price: float
    bar_idx: int
    cls: int = CLS_UNCLASSIFIED  # CLS_MAJOR, CLS_INTERNAL, CLS_UNCLASSIFIED
    broken: bool = False
    broken_bar: int = -1


@dataclass
class LiquidityPool:
    pool_type: int        # SWING_HIGH (BSL) or SWING_LOW (SSL)
    level: float
    start_bar: int
    swept: bool = False
    swept_bar: int = -1


@dataclass
class SMCState:
    """Full state machine matching PineScript 'State' type."""
    trend: int = TREND_UNDEFINED
    initialized: bool = False

    strong_low: float = float("nan")
    strong_high: float = float("nan")
    strong_low_bar: int = -1
    strong_high_bar: int = -1
    strong_low_idx: int = -1   # Index in swings array
    strong_high_idx: int = -1

    ref_high: float = float("nan")
    ref_low: float = float("nan")
    ref_high_bar: int = -1
    ref_low_bar: int = -1

    pending_bull_bos: bool = False
    pending_bull_bos_bar: int = -1
    pending_bear_bos: bool = False
    pending_bear_bos_bar: int = -1

    choch_ref_pending: bool = False
    choch_break_bar: int = -1

    ote_top: float = float("nan")
    ote_bottom: float = float("nan")
    equilibrium: float = float("nan")
    range_high: float = float("nan")
    range_low: float = float("nan")

    last_bos_bar: int = -1
    last_choch_bar: int = -1

    # Per-bar event flags
    alert_bull_bos: bool = False
    alert_bear_bos: bool = False
    alert_bull_choch: bool = False
    alert_bear_choch: bool = False
    alert_bsl_sweep: bool = False
    alert_ssl_sweep: bool = False


# ─── Default outputs ──────────────────────────────────────────────────

SMC_EMPTY: dict[str, float] = {
    "trend": 0.0,
    "strong_high": 0.0,
    "strong_low": 0.0,
    "ref_high": 0.0,
    "ref_low": 0.0,
    "equilibrium": 0.0,
    "ote_top": 0.0,
    "ote_bottom": 0.0,
    "zone": 0.0,          # +1 premium, -1 discount
    "bos_bull": 0.0,
    "bos_bear": 0.0,
    "choch_bull": 0.0,
    "choch_bear": 0.0,
}


# ─── Helper: check if value is NaN ───────────────────────────────────

def _isna(v: float) -> bool:
    return v != v  # NaN != NaN


def _nz(v: float, default: float = 0.0) -> float:
    return default if _isna(v) else v


# ─── Swing management ────────────────────────────────────────────────

def _add_swing(swings: list[SwingPoint], sw_type: int, price: float,
               bar_idx: int, swing_length: int, max_swings: int,
               st: SMCState) -> int:
    """Add a swing with alternation rule and re-detection guard.

    Returns index in swings array, or -1 if discarded.
    Matches PineScript addSwing() exactly.
    """
    count = len(swings)

    if count > 0:
        last = swings[-1]
        if last.swing_type == sw_type:
            # Same type: keep more extreme
            if sw_type == SWING_HIGH:
                if price >= last.price:
                    changed = price != last.price
                    last.price = price
                    last.bar_idx = bar_idx
                    if changed:
                        last.cls = CLS_UNCLASSIFIED
                        last.broken = False
                        last.broken_bar = -1
                    return count - 1
                return -1
            else:
                if price <= last.price:
                    changed = price != last.price
                    last.price = price
                    last.bar_idx = bar_idx
                    if changed:
                        last.cls = CLS_UNCLASSIFIED
                        last.broken = False
                        last.broken_bar = -1
                    return count - 1
                return -1
        else:
            # Different type: check re-detection
            search_depth = min(count, 2 * swing_length + 4)
            for s in range(count - 1, count - search_depth - 1, -1):
                if s < 0:
                    break
                sw = swings[s]
                if sw.bar_idx == bar_idx and sw.swing_type == sw_type:
                    if sw_type == SWING_HIGH and price >= sw.price:
                        changed = price != sw.price
                        sw.price = price
                        if changed:
                            sw.cls = CLS_UNCLASSIFIED
                            sw.broken = False
                            sw.broken_bar = -1
                    elif sw_type == SWING_LOW and price <= sw.price:
                        changed = price != sw.price
                        sw.price = price
                        if changed:
                            sw.cls = CLS_UNCLASSIFIED
                            sw.broken = False
                            sw.broken_bar = -1
                    return s

    # Append new swing
    swings.append(SwingPoint(sw_type, price, bar_idx))
    if len(swings) > max_swings:
        swings.pop(0)
        if st.strong_low_idx > 0:
            st.strong_low_idx -= 1
        elif st.strong_low_idx == 0:
            st.strong_low_idx = -1
        if st.strong_high_idx > 0:
            st.strong_high_idx -= 1
        elif st.strong_high_idx == 0:
            st.strong_high_idx = -1
    return len(swings) - 1


# ─── Search helpers ───────────────────────────────────────────────────

def _find_lowest_swing_low_between(swings: list[SwingPoint], bar_start: int, bar_end: int) -> int:
    candidate = -1
    for i in range(len(swings) - 1, -1, -1):
        sw = swings[i]
        if sw.bar_idx <= bar_start:
            break
        if sw.bar_idx >= bar_end:
            continue
        if sw.swing_type == SWING_LOW:
            if candidate == -1 or sw.price < swings[candidate].price:
                candidate = i
    return candidate


def _find_highest_swing_high_between(swings: list[SwingPoint], bar_start: int, bar_end: int) -> int:
    candidate = -1
    for i in range(len(swings) - 1, -1, -1):
        sw = swings[i]
        if sw.bar_idx <= bar_start:
            break
        if sw.bar_idx >= bar_end:
            continue
        if sw.swing_type == SWING_HIGH:
            if candidate == -1 or sw.price > swings[candidate].price:
                candidate = i
    return candidate


def _find_last_swing_high_before(swings: list[SwingPoint], bar: int) -> int:
    for i in range(len(swings) - 1, -1, -1):
        if swings[i].swing_type == SWING_HIGH and swings[i].bar_idx < bar:
            return i
    return -1


def _find_last_swing_low_before(swings: list[SwingPoint], bar: int) -> int:
    for i in range(len(swings) - 1, -1, -1):
        if swings[i].swing_type == SWING_LOW and swings[i].bar_idx < bar:
            return i
    return -1


def _find_lowest_bar_low_between(lows: np.ndarray, bar_start: int, bar_end: int) -> tuple[int, float]:
    """Bar-based search: find bar with absolute lowest low between two bars."""
    best_bar = -1
    best_price = float("nan")
    if bar_end > bar_start + 1:
        for j in range(bar_start + 1, bar_end):
            if j < 0 or j >= len(lows):
                continue
            if _isna(best_price) or lows[j] < best_price:
                best_price = float(lows[j])
                best_bar = j
    return best_bar, best_price


def _find_highest_bar_high_between(highs: np.ndarray, bar_start: int, bar_end: int) -> tuple[int, float]:
    best_bar = -1
    best_price = float("nan")
    if bar_end > bar_start + 1:
        for j in range(bar_start + 1, bar_end):
            if j < 0 or j >= len(highs):
                continue
            if _isna(best_price) or highs[j] > best_price:
                best_price = float(highs[j])
                best_bar = j
    return best_bar, best_price


def _find_swing_at_bar(swings: list[SwingPoint], target_bar: int, sw_type: int) -> int:
    for i in range(len(swings) - 1, -1, -1):
        if swings[i].bar_idx == target_bar and swings[i].swing_type == sw_type:
            return i
        if swings[i].bar_idx < target_bar:
            break
    return -1


# ─── Break detection ──────────────────────────────────────────────────

def _check_break_above(level: float, close: float, high: float, mode: str) -> bool:
    if _isna(level):
        return False
    return close > level if mode == "Close" else high > level


def _check_break_below(level: float, close: float, low: float, mode: str) -> bool:
    if _isna(level):
        return False
    return close < level if mode == "Close" else low < level


# ─── Zone computation ─────────────────────────────────────────────────

def _update_zones(st: SMCState) -> None:
    if st.trend == TREND_BULLISH:
        st.range_high = st.ref_high
        st.range_low = st.strong_low
    elif st.trend == TREND_BEARISH:
        st.range_high = st.strong_high
        st.range_low = st.ref_low

    if not _isna(st.range_high) and not _isna(st.range_low):
        st.equilibrium = (st.range_high + st.range_low) / 2.0


def _update_ote(st: SMCState, is_bullish: bool) -> None:
    if is_bullish:
        sw_low = st.strong_low
        sw_high = st.ref_high
    else:
        sw_high = st.strong_high
        sw_low = st.ref_low

    if not _isna(sw_high) and not _isna(sw_low):
        rng = sw_high - sw_low
        if rng > 0:
            if is_bullish:
                st.ote_top = sw_high - rng * 0.618
                st.ote_bottom = sw_high - rng * 0.786
            else:
                st.ote_top = sw_low + rng * 0.786
                st.ote_bottom = sw_low + rng * 0.618


def _clear_ote(st: SMCState) -> None:
    st.ote_top = float("nan")
    st.ote_bottom = float("nan")


# ─── Initialization ──────────────────────────────────────────────────

def _try_initialize(swings: list[SwingPoint], st: SMCState) -> bool:
    """Establish initial trend from first 4 alternating swings."""
    count = len(swings)
    if count < 4:
        return False

    for start in range(count - 3):
        s1, s2, s3, s4 = start, start + 1, start + 2, start + 3
        sw1, sw2, sw3, sw4 = swings[s1], swings[s2], swings[s3], swings[s4]

        # L-H-L-H pattern
        if (sw1.swing_type == SWING_LOW and sw2.swing_type == SWING_HIGH
                and sw3.swing_type == SWING_LOW and sw4.swing_type == SWING_HIGH):
            if sw4.price > sw2.price and sw3.price > sw1.price:
                st.trend = TREND_BULLISH
                st.strong_low = sw3.price
                st.strong_low_bar = sw3.bar_idx
                st.strong_low_idx = s3
                st.ref_high = sw4.price
                st.ref_high_bar = sw4.bar_idx
                for k in range(s1, s4 + 1):
                    swings[k].cls = CLS_MAJOR
                return True
            elif sw4.price < sw2.price and sw3.price < sw1.price:
                st.trend = TREND_BEARISH
                st.strong_high = sw2.price
                st.strong_high_bar = sw2.bar_idx
                st.strong_high_idx = s2
                st.ref_low = sw4.price
                st.ref_low_bar = sw4.bar_idx
                for k in range(s1, s4 + 1):
                    swings[k].cls = CLS_MAJOR
                return True

        # H-L-H-L pattern
        if (sw1.swing_type == SWING_HIGH and sw2.swing_type == SWING_LOW
                and sw3.swing_type == SWING_HIGH and sw4.swing_type == SWING_LOW):
            if sw3.price > sw1.price and sw4.price > sw2.price:
                st.trend = TREND_BULLISH
                st.strong_low = sw4.price
                st.strong_low_bar = sw4.bar_idx
                st.strong_low_idx = s4
                st.ref_high = sw3.price
                st.ref_high_bar = sw3.bar_idx
                for k in range(s1, s4 + 1):
                    swings[k].cls = CLS_MAJOR
                return True
            elif sw3.price < sw1.price and sw4.price < sw2.price:
                st.trend = TREND_BEARISH
                st.strong_high = sw1.price
                st.strong_high_bar = sw1.bar_idx
                st.strong_high_idx = s1
                st.ref_low = sw4.price
                st.ref_low_bar = sw4.bar_idx
                for k in range(s1, s4 + 1):
                    swings[k].cls = CLS_MAJOR
                return True

    # Fallback after 8 swings
    if count >= 8:
        first_sw = swings[0]
        last_sw = swings[-1]
        if last_sw.price > first_sw.price:
            st.trend = TREND_BULLISH
            sl_idx = _find_last_swing_low_before(swings, last_sw.bar_idx + 1)
            sh_idx = _find_last_swing_high_before(swings, last_sw.bar_idx + 1)
            if sl_idx >= 0:
                st.strong_low = swings[sl_idx].price
                st.strong_low_bar = swings[sl_idx].bar_idx
                st.strong_low_idx = sl_idx
            if sh_idx >= 0:
                st.ref_high = swings[sh_idx].price
                st.ref_high_bar = swings[sh_idx].bar_idx
        else:
            st.trend = TREND_BEARISH
            sh_idx = _find_last_swing_high_before(swings, last_sw.bar_idx + 1)
            sl_idx = _find_last_swing_low_before(swings, last_sw.bar_idx + 1)
            if sh_idx >= 0:
                st.strong_high = swings[sh_idx].price
                st.strong_high_bar = swings[sh_idx].bar_idx
                st.strong_high_idx = sh_idx
            if sl_idx >= 0:
                st.ref_low = swings[sl_idx].price
                st.ref_low_bar = swings[sl_idx].bar_idx
        for sw in swings:
            sw.cls = CLS_MAJOR
        return True

    return False


# ─── BOS firing ───────────────────────────────────────────────────────

def _fire_bullish_bos(st: SMCState, swings: list[SwingPoint],
                      lows: np.ndarray, break_bar: int) -> None:
    st.pending_bull_bos = True
    st.pending_bull_bos_bar = break_bar
    st.alert_bull_bos = True

    # Find HL: bar with lowest low in BOS range
    hl_bar, hl_price = _find_lowest_bar_low_between(lows, st.ref_high_bar, break_bar)
    if hl_bar >= 0 and not _isna(hl_price):
        st.strong_low = hl_price
        st.strong_low_bar = hl_bar
        hl_sw_idx = _find_swing_at_bar(swings, hl_bar, SWING_LOW)
        st.strong_low_idx = hl_sw_idx
        if hl_sw_idx >= 0:
            swings[hl_sw_idx].cls = CLS_MAJOR

    _update_zones(st)
    _update_ote(st, True)


def _fire_bearish_bos(st: SMCState, swings: list[SwingPoint],
                      highs: np.ndarray, break_bar: int) -> None:
    st.pending_bear_bos = True
    st.pending_bear_bos_bar = break_bar
    st.alert_bear_bos = True

    # Find LH: bar with highest high in BOS range
    lh_bar, lh_price = _find_highest_bar_high_between(highs, st.ref_low_bar, break_bar)
    if lh_bar >= 0 and not _isna(lh_price):
        st.strong_high = lh_price
        st.strong_high_bar = lh_bar
        lh_sw_idx = _find_swing_at_bar(swings, lh_bar, SWING_HIGH)
        st.strong_high_idx = lh_sw_idx
        if lh_sw_idx >= 0:
            swings[lh_sw_idx].cls = CLS_MAJOR

    _update_zones(st)
    _update_ote(st, False)


# ─── CHOCH processing ────────────────────────────────────────────────

def _process_bearish_choch(st: SMCState, swings: list[SwingPoint],
                           highs: np.ndarray, lows: np.ndarray,
                           break_bar: int) -> None:
    """Bull → Bear CHOCH (price broke below strong_low)."""
    st.trend = TREND_BEARISH
    st.alert_bear_choch = True

    # Strong high = ref_high from bullish trend
    if not _isna(st.ref_high):
        st.strong_high = st.ref_high
        st.strong_high_bar = st.ref_high_bar
        st.strong_high_idx = -1
        for k in range(len(swings) - 1, -1, -1):
            if swings[k].swing_type == SWING_HIGH and swings[k].bar_idx == st.ref_high_bar:
                st.strong_high_idx = k
                swings[k].cls = CLS_MAJOR
                break
    else:
        idx = _find_last_swing_high_before(swings, break_bar)
        if idx >= 0:
            swings[idx].cls = CLS_MAJOR
            st.strong_high = swings[idx].price
            st.strong_high_bar = swings[idx].bar_idx
            st.strong_high_idx = idx

    # Find reference low for new bearish trend
    sl_idx = _find_last_swing_low_before(swings, break_bar + 1)
    if sl_idx >= 0:
        st.ref_low = swings[sl_idx].price
        st.ref_low_bar = swings[sl_idx].bar_idx
        if swings[sl_idx].cls != CLS_MAJOR:
            swings[sl_idx].cls = CLS_MAJOR

    # Re-evaluation: if bullish BOS was pending
    if st.pending_bull_bos and st.ref_high_bar >= 0:
        actual_hh = _find_highest_swing_high_between(swings, st.ref_high_bar, break_bar + 1)
        hh_bar = swings[actual_hh].bar_idx if actual_hh >= 0 else break_bar

        better_hl_bar, better_hl_price = _find_lowest_bar_low_between(lows, st.ref_high_bar, hh_bar + 1)
        if better_hl_bar >= 0 and not _isna(better_hl_price):
            if _isna(st.strong_low) or better_hl_price < st.strong_low:
                st.strong_low = better_hl_price
                st.strong_low_bar = better_hl_bar
                sw_idx = _find_swing_at_bar(swings, better_hl_bar, SWING_LOW)
                st.strong_low_idx = sw_idx
                if sw_idx >= 0 and swings[sw_idx].cls != CLS_MAJOR:
                    swings[sw_idx].cls = CLS_MAJOR

        if actual_hh >= 0:
            hh_sw = swings[actual_hh]
            if hh_sw.cls != CLS_MAJOR:
                hh_sw.cls = CLS_MAJOR
            if hh_sw.price > st.strong_high or _isna(st.strong_high):
                st.strong_high = hh_sw.price
                st.strong_high_bar = hh_sw.bar_idx
                st.strong_high_idx = actual_hh

    # Clear bullish state
    st.strong_low = float("nan")
    st.strong_low_bar = -1
    st.strong_low_idx = -1
    st.ref_high = float("nan")
    st.ref_high_bar = -1
    st.pending_bull_bos = False
    st.pending_bull_bos_bar = -1
    st.choch_ref_pending = True
    st.choch_break_bar = break_bar
    _clear_ote(st)
    _update_zones(st)


def _process_bullish_choch(st: SMCState, swings: list[SwingPoint],
                           highs: np.ndarray, lows: np.ndarray,
                           break_bar: int) -> None:
    """Bear → Bull CHOCH (price broke above strong_high)."""
    st.trend = TREND_BULLISH
    st.alert_bull_choch = True

    # Strong low = ref_low from bearish trend
    if not _isna(st.ref_low):
        st.strong_low = st.ref_low
        st.strong_low_bar = st.ref_low_bar
        st.strong_low_idx = -1
        for k in range(len(swings) - 1, -1, -1):
            if swings[k].swing_type == SWING_LOW and swings[k].bar_idx == st.ref_low_bar:
                st.strong_low_idx = k
                swings[k].cls = CLS_MAJOR
                break
    else:
        idx = _find_last_swing_low_before(swings, break_bar)
        if idx >= 0:
            swings[idx].cls = CLS_MAJOR
            st.strong_low = swings[idx].price
            st.strong_low_bar = swings[idx].bar_idx
            st.strong_low_idx = idx

    # Find reference high for new bullish trend
    sh_idx = _find_last_swing_high_before(swings, break_bar + 1)
    if sh_idx >= 0:
        st.ref_high = swings[sh_idx].price
        st.ref_high_bar = swings[sh_idx].bar_idx
        if swings[sh_idx].cls != CLS_MAJOR:
            swings[sh_idx].cls = CLS_MAJOR

    # Re-evaluation: if bearish BOS was pending
    if st.pending_bear_bos and st.ref_low_bar >= 0:
        actual_ll = _find_lowest_swing_low_between(swings, st.ref_low_bar, break_bar + 1)
        ll_bar = swings[actual_ll].bar_idx if actual_ll >= 0 else break_bar

        better_lh_bar, better_lh_price = _find_highest_bar_high_between(highs, st.ref_low_bar, ll_bar + 1)
        if better_lh_bar >= 0 and not _isna(better_lh_price):
            if _isna(st.strong_high) or better_lh_price > st.strong_high:
                st.strong_high = better_lh_price
                st.strong_high_bar = better_lh_bar
                sw_idx = _find_swing_at_bar(swings, better_lh_bar, SWING_HIGH)
                st.strong_high_idx = sw_idx
                if sw_idx >= 0 and swings[sw_idx].cls != CLS_MAJOR:
                    swings[sw_idx].cls = CLS_MAJOR

        if actual_ll >= 0:
            ll_sw = swings[actual_ll]
            if ll_sw.cls != CLS_MAJOR:
                ll_sw.cls = CLS_MAJOR
            if ll_sw.price < st.strong_low or _isna(st.strong_low):
                st.strong_low = ll_sw.price
                st.strong_low_bar = ll_sw.bar_idx
                st.strong_low_idx = actual_ll

    # Clear bearish state
    st.strong_high = float("nan")
    st.strong_high_bar = -1
    st.strong_high_idx = -1
    st.ref_low = float("nan")
    st.ref_low_bar = -1
    st.pending_bear_bos = False
    st.pending_bear_bos_bar = -1
    st.choch_ref_pending = True
    st.choch_break_bar = break_bar
    _clear_ote(st)
    _update_zones(st)


# ─── State machine — swing classification ─────────────────────────────

def _process_swing(st: SMCState, swings: list[SwingPoint], swing_idx: int,
                   current_bar: int, highs: np.ndarray, lows: np.ndarray,
                   closes: np.ndarray, break_mode: str) -> None:
    """Core state machine matching PineScript processSwingInStateMachine."""
    if not st.initialized or swing_idx < 0 or swing_idx >= len(swings):
        return

    sw = swings[swing_idx]
    sw_type = sw.swing_type
    sw_bar = sw.bar_idx

    choch_handled = False

    # ── CHOCH reference handling ──
    if st.choch_ref_pending:
        if st.trend == TREND_BULLISH and sw_type == SWING_HIGH:
            st.ref_high = sw.price
            st.ref_high_bar = sw.bar_idx
            sw.cls = CLS_INTERNAL
            st.choch_ref_pending = False
            st.choch_break_bar = -1
            st.pending_bull_bos = False
            st.pending_bull_bos_bar = -1
            _update_zones(st)
            choch_handled = True

        elif st.trend == TREND_BEARISH and sw_type == SWING_LOW:
            st.ref_low = sw.price
            st.ref_low_bar = sw.bar_idx
            sw.cls = CLS_INTERNAL
            st.choch_ref_pending = False
            st.choch_break_bar = -1
            st.pending_bear_bos = False
            st.pending_bear_bos_bar = -1
            _update_zones(st)
            choch_handled = True

        # Late swing handler
        elif (st.trend == TREND_BEARISH and sw_type == SWING_HIGH
              and not _isna(st.strong_high) and sw.price > st.strong_high):
            sw.cls = CLS_MAJOR
            prev_sh_bar = st.strong_high_bar
            st.strong_high = sw.price
            st.strong_high_bar = sw.bar_idx
            st.strong_high_idx = swing_idx
            # Find HL between old strong_high and this new HH
            hl_bar, hl_price = _find_lowest_bar_low_between(lows, prev_sh_bar, sw.bar_idx)
            if hl_bar >= 0 and not _isna(hl_price):
                hl_idx = _find_swing_at_bar(swings, hl_bar, SWING_LOW)
                if hl_idx >= 0 and swings[hl_idx].cls != CLS_MAJOR:
                    swings[hl_idx].cls = CLS_MAJOR
            choch_handled = True

        elif (st.trend == TREND_BULLISH and sw_type == SWING_LOW
              and not _isna(st.strong_low) and sw.price < st.strong_low):
            sw.cls = CLS_MAJOR
            prev_sl_bar = st.strong_low_bar
            st.strong_low = sw.price
            st.strong_low_bar = sw.bar_idx
            st.strong_low_idx = swing_idx
            lh_bar, lh_price = _find_highest_bar_high_between(highs, prev_sl_bar, sw.bar_idx)
            if lh_bar >= 0 and not _isna(lh_price):
                lh_idx = _find_swing_at_bar(swings, lh_bar, SWING_HIGH)
                if lh_idx >= 0 and swings[lh_idx].cls != CLS_MAJOR:
                    swings[lh_idx].cls = CLS_MAJOR
            choch_handled = True

    # ── Normal classification ──
    if not choch_handled:
        if st.trend == TREND_BULLISH:
            if sw_type == SWING_HIGH:
                if not _isna(st.ref_high) and sw.price > st.ref_high:
                    # HH confirmed
                    if not st.pending_bull_bos:
                        # Find actual break bar
                        brk = -1
                        for j in range(st.ref_high_bar + 1, current_bar + 1):
                            if j < len(closes) and _check_break_above(st.ref_high, closes[j], highs[j], break_mode):
                                brk = j
                                break
                        if brk < 0:
                            brk = sw_bar
                        _fire_bullish_bos(st, swings, lows, brk)

                    sw.cls = CLS_MAJOR

                    # Promote HL
                    hl_bar, hl_price = _find_lowest_bar_low_between(lows, st.ref_high_bar, sw_bar)
                    if hl_bar >= 0 and not _isna(hl_price):
                        st.strong_low = hl_price
                        st.strong_low_bar = hl_bar
                        hl_idx = _find_swing_at_bar(swings, hl_bar, SWING_LOW)
                        st.strong_low_idx = hl_idx
                        if hl_idx >= 0 and swings[hl_idx].cls != CLS_MAJOR:
                            swings[hl_idx].cls = CLS_MAJOR

                    # Update ref_high
                    st.ref_high = sw.price
                    st.ref_high_bar = sw_bar
                    st.pending_bull_bos = False
                    st.pending_bull_bos_bar = -1
                    _update_zones(st)
                    _update_ote(st, True)

                    # Retroactive break check
                    if st.ref_high_bar + 1 <= current_bar:
                        for j in range(st.ref_high_bar + 1, current_bar + 1):
                            if j < len(closes) and _check_break_above(st.ref_high, closes[j], highs[j], break_mode):
                                _fire_bullish_bos(st, swings, lows, j)
                                break
                else:
                    sw.cls = CLS_INTERNAL
            else:
                sw.cls = CLS_INTERNAL

        elif st.trend == TREND_BEARISH:
            if sw_type == SWING_LOW:
                if not _isna(st.ref_low) and sw.price < st.ref_low:
                    # LL confirmed
                    if not st.pending_bear_bos:
                        brk = -1
                        for j in range(st.ref_low_bar + 1, current_bar + 1):
                            if j < len(closes) and _check_break_below(st.ref_low, closes[j], lows[j], break_mode):
                                brk = j
                                break
                        if brk < 0:
                            brk = sw_bar
                        _fire_bearish_bos(st, swings, highs, brk)

                    sw.cls = CLS_MAJOR

                    # Promote LH
                    lh_bar, lh_price = _find_highest_bar_high_between(highs, st.ref_low_bar, sw_bar)
                    if lh_bar >= 0 and not _isna(lh_price):
                        st.strong_high = lh_price
                        st.strong_high_bar = lh_bar
                        lh_idx = _find_swing_at_bar(swings, lh_bar, SWING_HIGH)
                        st.strong_high_idx = lh_idx
                        if lh_idx >= 0 and swings[lh_idx].cls != CLS_MAJOR:
                            swings[lh_idx].cls = CLS_MAJOR

                    st.ref_low = sw.price
                    st.ref_low_bar = sw_bar
                    st.pending_bear_bos = False
                    st.pending_bear_bos_bar = -1
                    _update_zones(st)
                    _update_ote(st, False)

                    # Retroactive break check
                    if st.ref_low_bar + 1 <= current_bar:
                        for j in range(st.ref_low_bar + 1, current_bar + 1):
                            if j < len(closes) and _check_break_below(st.ref_low, closes[j], lows[j], break_mode):
                                _fire_bearish_bos(st, swings, highs, j)
                                break
                else:
                    sw.cls = CLS_INTERNAL
            else:
                sw.cls = CLS_INTERNAL
        else:
            sw.cls = CLS_INTERNAL


# ─── Liquidity detection ─────────────────────────────────────────────

def _scan_liquidity_pools(swings: list[SwingPoint], eq_threshold: float,
                          min_touches: int) -> list[LiquidityPool]:
    """Scan for Equal Highs/Lows (EQH/EQL) liquidity pools."""
    pools: list[LiquidityPool] = []
    count = len(swings)

    # Scan highs (BSL)
    for i in range(count - 1, -1, -1):
        sw_i = swings[i]
        if sw_i.swing_type != SWING_HIGH:
            continue
        # Check if already in a pool
        in_pool = any(p.pool_type == SWING_HIGH and abs(sw_i.price - p.level) <= eq_threshold
                      for p in pools)
        if in_pool:
            continue

        touch_count = 0
        price_sum = 0.0
        first_bar = sw_i.bar_idx
        for j in range(count):
            sw_j = swings[j]
            if sw_j.swing_type == SWING_HIGH and abs(sw_i.price - sw_j.price) <= eq_threshold:
                touch_count += 1
                price_sum += sw_j.price
                if sw_j.bar_idx < first_bar:
                    first_bar = sw_j.bar_idx
        if touch_count >= min_touches:
            pools.append(LiquidityPool(SWING_HIGH, price_sum / touch_count, first_bar))

    # Scan lows (SSL)
    for i in range(count - 1, -1, -1):
        sw_i = swings[i]
        if sw_i.swing_type != SWING_LOW:
            continue
        in_pool = any(p.pool_type == SWING_LOW and abs(sw_i.price - p.level) <= eq_threshold
                      for p in pools)
        if in_pool:
            continue

        touch_count = 0
        price_sum = 0.0
        first_bar = sw_i.bar_idx
        for j in range(count):
            sw_j = swings[j]
            if sw_j.swing_type == SWING_LOW and abs(sw_i.price - sw_j.price) <= eq_threshold:
                touch_count += 1
                price_sum += sw_j.price
                if sw_j.bar_idx < first_bar:
                    first_bar = sw_j.bar_idx
        if touch_count >= min_touches:
            pools.append(LiquidityPool(SWING_LOW, price_sum / touch_count, first_bar))

    return pools


def _check_sweeps(pools: list[LiquidityPool], high: float, low: float,
                  close: float, bar_idx: int, st: SMCState) -> None:
    """Check for liquidity sweeps on current bar."""
    for pool in pools:
        if pool.swept:
            continue
        if pool.pool_type == SWING_HIGH:
            if high > pool.level and close < pool.level:
                pool.swept = True
                pool.swept_bar = bar_idx
                st.alert_bsl_sweep = True
        else:
            if low < pool.level and close > pool.level:
                pool.swept = True
                pool.swept_bar = bar_idx
                st.alert_ssl_sweep = True


# ─── Pivot detection (matching ta.pivothigh / ta.pivotlow) ────────────

def _pivot_high(highs: np.ndarray, i: int, length: int) -> float | None:
    """Detect pivot high at bar i-length (confirmed at bar i)."""
    pivot_bar = i - length
    if pivot_bar < length or pivot_bar >= len(highs):
        return None

    pivot_val = highs[pivot_bar]
    # Check left side
    for j in range(pivot_bar - length, pivot_bar):
        if j < 0:
            return None
        if highs[j] > pivot_val:
            return None
    # Check right side
    for j in range(pivot_bar + 1, pivot_bar + length + 1):
        if j >= len(highs):
            return None
        if highs[j] > pivot_val:
            return None
    return float(pivot_val)


def _pivot_low(lows: np.ndarray, i: int, length: int) -> float | None:
    """Detect pivot low at bar i-length (confirmed at bar i)."""
    pivot_bar = i - length
    if pivot_bar < length or pivot_bar >= len(lows):
        return None

    pivot_val = lows[pivot_bar]
    for j in range(pivot_bar - length, pivot_bar):
        if j < 0:
            return None
        if lows[j] < pivot_val:
            return None
    for j in range(pivot_bar + 1, pivot_bar + length + 1):
        if j >= len(lows):
            return None
        if lows[j] < pivot_val:
            return None
    return float(pivot_val)


# ═══════════════════════════════════════════════════════════════════════
# Main simulation — runs bar-by-bar matching PineScript main logic
# ═══════════════════════════════════════════════════════════════════════

def _run_smc_simulation(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                        swing_length: int, break_mode: str, max_swings: int,
                        eq_atr_mult: float, eq_min_touches: int,
                        n_bars: int | None = None
                        ) -> tuple[SMCState, list[SwingPoint], list[LiquidityPool], list[dict[str, float]]]:
    """Run the full SMC simulation, collecting per-bar output values.

    Returns (final_state, swings, liq_pools, per_bar_outputs).
    """
    n = n_bars if n_bars is not None else len(highs)
    st = SMCState()
    swings: list[SwingPoint] = []
    liq_pools: list[LiquidityPool] = []
    outputs: list[dict[str, float]] = []

    # ATR for liquidity threshold (simple implementation)
    atr_vals = np.full(n, 0.0)
    if n > 14:
        for i in range(1, n):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]) if i > 0 else highs[i] - lows[i],
                     abs(lows[i] - closes[i - 1]) if i > 0 else highs[i] - lows[i])
            if i < 14:
                atr_vals[i] = tr
            else:
                atr_vals[i] = (atr_vals[i - 1] * 13 + tr) / 14

    for i in range(n):
        # Reset per-bar flags
        st.alert_bull_bos = False
        st.alert_bear_bos = False
        st.alert_bull_choch = False
        st.alert_bear_choch = False
        st.alert_bsl_sweep = False
        st.alert_ssl_sweep = False

        # ── STEP 1: Per-bar break detection ──
        if st.initialized:
            # CHOCH checks
            if st.trend == TREND_BULLISH and not _isna(st.strong_low):
                if _check_break_below(st.strong_low, closes[i], lows[i], break_mode) and i != st.last_choch_bar:
                    st.last_choch_bar = i
                    _process_bearish_choch(st, swings, highs, lows, i)

            if st.trend == TREND_BEARISH and not _isna(st.strong_high):
                if _check_break_above(st.strong_high, closes[i], highs[i], break_mode) and i != st.last_choch_bar:
                    st.last_choch_bar = i
                    _process_bullish_choch(st, swings, highs, lows, i)

            # BOS checks
            if (st.trend == TREND_BULLISH and not _isna(st.ref_high)
                    and not st.pending_bull_bos and not st.choch_ref_pending):
                if _check_break_above(st.ref_high, closes[i], highs[i], break_mode) and i != st.last_bos_bar:
                    st.last_bos_bar = i
                    _fire_bullish_bos(st, swings, lows, i)

            if (st.trend == TREND_BEARISH and not _isna(st.ref_low)
                    and not st.pending_bear_bos and not st.choch_ref_pending):
                if _check_break_below(st.ref_low, closes[i], lows[i], break_mode) and i != st.last_bos_bar:
                    st.last_bos_bar = i
                    _fire_bearish_bos(st, swings, highs, i)

        # ── STEP 2: Swing detection + classification ──
        swing_bar = i - swing_length
        new_swing = False

        ph = _pivot_high(highs, i, swing_length)
        if ph is not None:
            sw_idx = _add_swing(swings, SWING_HIGH, ph, swing_bar, swing_length, max_swings, st)
            if sw_idx >= 0 and sw_idx < len(swings):
                sw = swings[sw_idx]
                if sw.cls == CLS_UNCLASSIFIED:
                    if not st.initialized:
                        if _try_initialize(swings, st):
                            st.initialized = True
                            _update_zones(st)
                    else:
                        _process_swing(st, swings, sw_idx, i, highs, lows, closes, break_mode)
            new_swing = True

        pl = _pivot_low(lows, i, swing_length)
        if pl is not None:
            sw_idx = _add_swing(swings, SWING_LOW, pl, swing_bar, swing_length, max_swings, st)
            if sw_idx >= 0 and sw_idx < len(swings):
                sw = swings[sw_idx]
                if sw.cls == CLS_UNCLASSIFIED:
                    if not st.initialized:
                        if _try_initialize(swings, st):
                            st.initialized = True
                            _update_zones(st)
                    else:
                        _process_swing(st, swings, sw_idx, i, highs, lows, closes, break_mode)
            new_swing = True

        # ── STEP 3: Liquidity ──
        if new_swing:
            eq_threshold = atr_vals[i] * eq_atr_mult if atr_vals[i] > 0 else 1.0
            liq_pools = _scan_liquidity_pools(swings, eq_threshold, eq_min_touches)
        _check_sweeps(liq_pools, float(highs[i]), float(lows[i]), float(closes[i]), i, st)

        # ── Collect output for this bar ──
        zone = 0.0
        if not _isna(st.equilibrium):
            zone = 1.0 if closes[i] > st.equilibrium else -1.0

        outputs.append({
            "trend": float(st.trend),
            "strong_high": _nz(st.strong_high),
            "strong_low": _nz(st.strong_low),
            "ref_high": _nz(st.ref_high),
            "ref_low": _nz(st.ref_low),
            "equilibrium": _nz(st.equilibrium),
            "ote_top": _nz(st.ote_top),
            "ote_bottom": _nz(st.ote_bottom),
            "zone": zone,
            "bos_bull": 1.0 if st.alert_bull_bos else 0.0,
            "bos_bear": 1.0 if st.alert_bear_bos else 0.0,
            "choch_bull": 1.0 if st.alert_bull_choch else 0.0,
            "choch_bear": 1.0 if st.alert_bear_choch else 0.0,
        })

    return st, swings, liq_pools, outputs


# ═══════════════════════════════════════════════════════════════════════
# compute_at — bar-by-bar for strategy engine
# ═══════════════════════════════════════════════════════════════════════

def smc_structure_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute SMC Structure at the last bar of the slice."""
    swing_length = params.get("swing_length", 5)
    break_mode = params.get("break_mode", "Wick")
    max_swings = params.get("max_swings", 200)
    eq_atr_mult = params.get("eq_atr_mult", 0.1)
    eq_min_touches = params.get("eq_min_touches", 2)

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    if n < swing_length * 2 + 1:
        return dict(SMC_EMPTY)

    _, _, _, outputs = _run_smc_simulation(
        highs, lows, closes, swing_length, break_mode, max_swings,
        eq_atr_mult, eq_min_touches,
    )

    return outputs[-1] if outputs else dict(SMC_EMPTY)


# ═══════════════════════════════════════════════════════════════════════
# compute_series — full array for charting
# ═══════════════════════════════════════════════════════════════════════

def smc_structure_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute SMC Structure over all bars for chart overlay."""
    swing_length = params.get("swing_length", 5)
    break_mode = params.get("break_mode", "Wick")
    max_swings = params.get("max_swings", 200)
    eq_atr_mult = params.get("eq_atr_mult", 0.1)
    eq_min_touches = params.get("eq_min_touches", 2)

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    empty = {k: [None] * n for k in SMC_EMPTY}
    if n < swing_length * 2 + 1:
        return empty

    st, swings_list, _, outputs = _run_smc_simulation(
        highs, lows, closes, swing_length, break_mode, max_swings,
        eq_atr_mult, eq_min_touches,
    )

    # Convert outputs list to dict of lists
    result: dict[str, list[float | None]] = {k: [None] * n for k in SMC_EMPTY}

    # Add swing point markers
    result["swing_high"] = [None] * n
    result["swing_low"] = [None] * n

    for i, out in enumerate(outputs):
        for k, v in out.items():
            if k in result:
                result[k][i] = v if v != 0.0 else None

    # Keep carry-forward levels (don't null out zeros for these)
    for key in ("trend", "strong_high", "strong_low", "ref_high", "ref_low",
                "equilibrium", "ote_top", "ote_bottom"):
        for i, out in enumerate(outputs):
            result[key][i] = out.get(key)
            # Convert 0.0 back to None only if the level was never set
            if result[key][i] == 0.0 and key != "trend":
                result[key][i] = None

    # Mark swing points
    for sw in swings_list:
        if 0 <= sw.bar_idx < n:
            if sw.swing_type == SWING_HIGH:
                result["swing_high"][sw.bar_idx] = sw.price
            else:
                result["swing_low"][sw.bar_idx] = sw.price

    return result
