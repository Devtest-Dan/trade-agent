"""Elliott Wave Multi-Degree Indicator — trade-agent wrapper.

Wraps the standalone ElliottWave engine (D:\\ElliottWave) for use
in the trade-agent backtest/strategy system.

Outputs 77 fields per bar covering 5 degrees (Minute, Minor, Intermediate,
Primary, Cycle) with preferred + alternate wave counts, Fibonacci levels,
and event flags.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

# Add ElliottWave project to sys.path so we can import it
_EW_ROOT = Path("D:/ElliottWave")
if str(_EW_ROOT) not in sys.path:
    sys.path.insert(0, str(_EW_ROOT))

from elliott_wave.core.engine import run_simulation, _make_degree_state, _collect_output  # noqa: E402
from elliott_wave.core.constants import (  # noqa: E402
    DEGREE_CONFIGS, MODE_IMPULSE, MODE_CORRECTIVE, DegreeConfig,
    SWING_HIGH, SWING_LOW,
    WAVE_1, WAVE_2, WAVE_3, WAVE_4, WAVE_5, WAVE_A, WAVE_B, WAVE_C,
)
from elliott_wave.core.models import EWDegreeState  # noqa: E402

# ─── Empty output (all 77 fields at 0.0) ──────────────────────────────

ELLIOTT_EMPTY: dict[str, float] = {}
for _cfg in DEGREE_CONFIGS:
    _p = _cfg.name
    ELLIOTT_EMPTY.update({
        f"{_p}_pref_wave": 0.0, f"{_p}_pref_mode": 0.0, f"{_p}_pref_direction": 0.0,
        f"{_p}_pref_confidence": 0.0, f"{_p}_pref_invalidation": 0.0,
        f"{_p}_alt_wave": 0.0, f"{_p}_alt_mode": 0.0, f"{_p}_alt_confidence": 0.0,
        f"{_p}_fib_target_100": 0.0, f"{_p}_fib_target_1618": 0.0,
        f"{_p}_fib_retrace_382": 0.0, f"{_p}_fib_retrace_618": 0.0,
        f"{_p}_truncated": 0.0, f"{_p}_wave_complete": 0.0,
    })
ELLIOTT_EMPTY.update({
    "parent_degree": 0.0, "parent_wave": 0.0, "parent_direction": 0.0,
    "impulse_complete": 0.0, "correction_complete": 0.0,
    "count_invalidated": 0.0, "count_switched": 0.0,
})


# ─── Single-bar compute (for bar-by-bar backtest) ─────────────────────

def elliott_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute Elliott Wave at the last bar of the DataFrame slice."""
    if len(df) < 10:
        return dict(ELLIOTT_EMPTY)

    try:
        swing_lengths = params.get("swing_lengths", None)
        max_swings = params.get("max_swings", 200)

        outputs = run_simulation(df, swing_lengths=swing_lengths, max_swings=max_swings)
        if not outputs:
            return dict(ELLIOTT_EMPTY)
        return outputs[-1]
    except Exception as e:
        logger.warning(f"ElliottWave computation failed: {e}")
        return dict(ELLIOTT_EMPTY)


# ─── Full-series compute (for charting) ────────────────────────────────

_WAVE_LABELS = {
    WAVE_1: "1", WAVE_2: "2", WAVE_3: "3", WAVE_4: "4", WAVE_5: "5",
    WAVE_A: "A", WAVE_B: "B", WAVE_C: "C",
}

_DEGREE_COLORS = {
    "cycle": "#e74c3c",        # red
    "primary": "#e67e22",      # orange
    "intermediate": "#3498db", # blue
    "minor": "#2ecc71",        # green
    "minute": "#95a5a6",       # gray
}


def elliott_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute Elliott Wave over all bars for chart overlay with markers."""
    n = len(df)
    empty = {k: [None] * n for k in ELLIOTT_EMPTY}

    if n < 10:
        return empty

    try:
        swing_lengths = params.get("swing_lengths", None)
        max_swings = params.get("max_swings", 200)

        outputs = run_simulation(df, swing_lengths=swing_lengths, max_swings=max_swings)

        if not outputs:
            return empty

        result: dict[str, list[float | None]] = {k: [None] * n for k in ELLIOTT_EMPTY}
        for i, row in enumerate(outputs):
            for k, v in row.items():
                if k in result:
                    result[k][i] = v

        # ── Build wave label markers for the chart ──
        # Re-run the engine to get access to degree states with swing/pivot data
        from elliott_wave.core.engine import run_simulation as _run  # noqa
        from elliott_wave.core.zigzag import pivot_high, pivot_low, add_swing
        from elliott_wave.core.wave_counter import process_swing, initiate_count, check_invalidation
        from elliott_wave.core.reconciler import reconcile_degrees
        from elliott_wave.core.rules import compute_confidence

        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)
        closes = df["close"].values.astype(float)

        configs = list(DEGREE_CONFIGS)
        if swing_lengths and len(swing_lengths) == len(configs):
            configs = [DegreeConfig(c.index, c.name, sl) for c, sl in zip(configs, swing_lengths)]

        degrees = [_make_degree_state(cfg, max_swings) for cfg in configs]
        markers = []

        for i in range(n):
            for ds in degrees:
                ds.wave_completed = False
                ds.completed_wave_num = 0
                ds.count_invalidated = False
                ds.count_switched = False

            for ds in degrees:
                if ds.initialized:
                    check_invalidation(ds, current_price=closes[i], bar_idx=i)

                ph = pivot_high(highs, i, ds.swing_length)
                if ph is not None:
                    swing_bar = i - ds.swing_length
                    sw_idx = add_swing(ds.swings, SWING_HIGH, ph, swing_bar,
                                       ds.swing_length, ds.max_swings)
                    if sw_idx >= 0:
                        sw = ds.swings[sw_idx]
                        if not ds.initialized:
                            initiate_count(ds, bar_idx=i)
                        else:
                            process_swing(ds, sw, bar_idx=i)

                pl = pivot_low(lows, i, ds.swing_length)
                if pl is not None:
                    swing_bar = i - ds.swing_length
                    sw_idx = add_swing(ds.swings, SWING_LOW, pl, swing_bar,
                                       ds.swing_length, ds.max_swings)
                    if sw_idx >= 0:
                        sw = ds.swings[sw_idx]
                        if not ds.initialized:
                            initiate_count(ds, bar_idx=i)
                        else:
                            process_swing(ds, sw, bar_idx=i)

            reconcile_degrees(degrees, bar_idx=i)

        # Extract wave label markers from completed counts and current pivots
        for ds in degrees:
            color = _DEGREE_COLORS.get(ds.degree_name, "#95a5a6")
            all_counts = ds.completed_counts + [ds.preferred]
            for wc in all_counts:
                for i_pv, pivot in enumerate(wc.pivots):
                    # First pivot is the origin — label it "0"
                    if i_pv == 0:
                        if 0 <= pivot.bar_idx < n:
                            markers.append({
                                "bar": pivot.bar_idx,
                                "price": pivot.price,
                                "label": "0",
                                "color": color,
                                "position": "belowBar" if pivot.swing_type == SWING_LOW else "aboveBar",
                            })
                        continue
                    label_str = _WAVE_LABELS.get(pivot.wave_label, "")
                    if label_str and 0 <= pivot.bar_idx < n:
                        markers.append({
                            "bar": pivot.bar_idx,
                            "price": pivot.price,
                            "label": label_str,
                            "color": color,
                            "position": "aboveBar" if pivot.swing_type == SWING_HIGH else "belowBar",
                        })

        # Add invalidation level as a price line marker
        for ds in degrees:
            wc = ds.preferred
            inv = wc.invalidation_level
            if inv == inv and inv != 0.0:  # not NaN
                result[f"{ds.degree_name}_pref_invalidation"] = [inv] * n

        result["_markers"] = markers  # type: ignore[assignment]
        return result
    except Exception as e:
        logger.warning(f"ElliottWave series computation failed: {e}")
        return empty
