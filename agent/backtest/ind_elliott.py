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

from elliott_wave.core.engine import run_simulation  # noqa: E402
from elliott_wave.core.constants import DEGREE_CONFIGS, MODE_IMPULSE  # noqa: E402

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

def elliott_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute Elliott Wave over all bars for chart overlay."""
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

        return result
    except Exception as e:
        logger.warning(f"ElliottWave series computation failed: {e}")
        return empty
