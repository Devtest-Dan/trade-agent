"""SMC + Elliott Wave Confluence Indicator.

Meta-indicator that reads SMC and Elliott Wave outputs from the same bar
and computes confluence scores. Does NOT run its own zigzag — it operates
on pre-computed outputs from ind_smc and ind_elliott.

Confluence signals:
- EW wave 3 starting + SMC bullish BOS → strong trend continuation
- EW wave 2 end at SMC order block → institutional + wave alignment
- EW wave 5 forming + SMC CHoCH → exhaustion / reversal
- EW correction at SMC FVG → correction bounce opportunity
- EW wave count direction matches SMC trend → directional agreement
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from agent.backtest.ind_smc import SMC_EMPTY, smc_structure_at, smc_structure_series
from agent.backtest.ind_elliott import ELLIOTT_EMPTY, elliott_at, elliott_series

# ─── Constants ──────────────────────────────────────────────────────────

# EW wave labels
_W1, _W2, _W3, _W4, _W5 = 1.0, 2.0, 3.0, 4.0, 5.0
_WA, _WB, _WC = 6.0, 7.0, 8.0

# SMC trend
_TREND_BULL, _TREND_BEAR = 1.0, -1.0

# Confluence weights
W_TREND_AGREE = 0.25       # SMC trend matches EW direction
W_BOS_WAVE3 = 0.20         # BOS fires during EW wave 3
W_CHOCH_WAVE5 = 0.20       # CHoCH fires during EW wave 5 or correction
W_OB_WAVE_END = 0.15       # price at OB zone when EW corrective wave ends
W_FVG_CORRECTION = 0.10    # price at FVG during EW correction
W_ZONE_AGREE = 0.10        # SMC zone (premium/discount) aligns with EW direction


# ─── Empty output ───────────────────────────────────────────────────────

SMC_EW_EMPTY: dict[str, float] = {
    # Overall confluence
    "confluence_score": 0.0,          # 0.0 - 1.0 weighted agreement
    "confluence_direction": 0.0,      # +1 buy, -1 sell, 0 neutral

    # Component scores (each 0.0 or 1.0)
    "trend_agreement": 0.0,           # SMC trend matches EW direction
    "zone_agreement": 0.0,            # premium/discount aligns with wave

    # Specific confluence events (fire for one bar only)
    "ew_w3_with_bos": 0.0,           # EW wave 3 active + SMC bullish/bearish BOS
    "ew_w2_at_ob": 0.0,              # EW wave 2 complete + price at active OB
    "ew_w4_at_ob": 0.0,              # EW wave 4 complete + price at active OB
    "ew_w5_exhaustion": 0.0,         # EW wave 5 + SMC CHoCH = reversal
    "ew_correction_at_fvg": 0.0,     # A-B-C correction + FVG alignment

    # Highest-confidence degree info
    "best_degree_idx": 0.0,          # degree index with highest confidence
    "best_degree_wave": 0.0,         # wave number at that degree
    "best_degree_confidence": 0.0,   # confidence at that degree
    "best_degree_direction": 0.0,    # direction at that degree
}


# ─── Degree names for field lookup ──────────────────────────────────────

_DEGREES = ["minute", "minor", "intermediate", "primary", "cycle"]


def _get_best_degree(ew: dict[str, float]) -> tuple[int, float, float, float]:
    """Find the degree with highest preferred confidence.

    Returns (degree_idx, wave, confidence, direction).
    """
    best_idx, best_wave, best_conf, best_dir = 0, 0.0, 0.0, 0.0
    for i, deg in enumerate(_DEGREES):
        conf = ew.get(f"{deg}_pref_confidence", 0.0)
        if conf > best_conf:
            best_conf = conf
            best_idx = i
            best_wave = ew.get(f"{deg}_pref_wave", 0.0)
            best_dir = ew.get(f"{deg}_pref_direction", 0.0)
    return best_idx, best_wave, best_conf, best_dir


def _compute_confluence(smc: dict[str, float], ew: dict[str, float]) -> dict[str, float]:
    """Compute confluence between SMC and EW outputs for one bar."""
    out = dict(SMC_EW_EMPTY)

    # Find the best (highest confidence) EW degree
    best_idx, best_wave, best_conf, best_dir = _get_best_degree(ew)
    out["best_degree_idx"] = float(best_idx)
    out["best_degree_wave"] = best_wave
    out["best_degree_confidence"] = best_conf
    out["best_degree_direction"] = best_dir

    smc_trend = smc.get("trend", 0.0)
    smc_zone = smc.get("zone", 0.0)
    bos_bull = smc.get("bos_bull", 0.0)
    bos_bear = smc.get("bos_bear", 0.0)
    choch_bull = smc.get("choch_bull", 0.0)
    choch_bear = smc.get("choch_bear", 0.0)
    ob_state = smc.get("ob_state", 0.0)
    ob_type = smc.get("ob_type", 0.0)
    fvg_type = smc.get("fvg_type", 0.0)

    score = 0.0

    # 1. Trend agreement: SMC trend matches EW direction
    if best_dir != 0.0 and smc_trend != 0.0:
        if best_dir == smc_trend:
            out["trend_agreement"] = 1.0
            score += W_TREND_AGREE

    # 2. Zone agreement: SMC premium/discount aligns with EW wave direction
    #    Up direction + discount zone = good entry; Down direction + premium zone = good entry
    if best_dir != 0.0 and smc_zone != 0.0:
        if (best_dir == 1.0 and smc_zone == -1.0) or (best_dir == -1.0 and smc_zone == 1.0):
            out["zone_agreement"] = 1.0
            score += W_ZONE_AGREE

    # 3. BOS + Wave 3: BOS fires while EW is in wave 3 (strongest impulse wave)
    if best_wave == _W3:
        if best_dir == 1.0 and bos_bull == 1.0:
            out["ew_w3_with_bos"] = 1.0
            score += W_BOS_WAVE3
        elif best_dir == -1.0 and bos_bear == 1.0:
            out["ew_w3_with_bos"] = 1.0
            score += W_BOS_WAVE3

    # 4. Wave 2 end at OB: corrective wave ending at institutional order block
    if best_wave == _W2 and ob_state in (1.0, 2.0):  # active or tested OB
        # Bullish OB + up direction = wave 2 pullback to demand
        if ob_type == 1.0 and best_dir == 1.0:
            out["ew_w2_at_ob"] = 1.0
            score += W_OB_WAVE_END
        # Bearish OB + down direction = wave 2 pullback to supply
        elif ob_type == -1.0 and best_dir == -1.0:
            out["ew_w2_at_ob"] = 1.0
            score += W_OB_WAVE_END

    # 5. Wave 4 end at OB: same logic for wave 4
    if best_wave == _W4 and ob_state in (1.0, 2.0):
        if ob_type == 1.0 and best_dir == 1.0:
            out["ew_w4_at_ob"] = 1.0
            score += W_OB_WAVE_END
        elif ob_type == -1.0 and best_dir == -1.0:
            out["ew_w4_at_ob"] = 1.0
            score += W_OB_WAVE_END

    # 6. Wave 5 exhaustion + CHoCH: wave 5 forming/complete + SMC reversal signal
    if best_wave == _W5:
        if best_dir == 1.0 and choch_bear == 1.0:
            out["ew_w5_exhaustion"] = 1.0
            score += W_CHOCH_WAVE5
        elif best_dir == -1.0 and choch_bull == 1.0:
            out["ew_w5_exhaustion"] = 1.0
            score += W_CHOCH_WAVE5

    # Also check for CHoCH during A-B-C correction (reversal opportunity)
    if best_wave in (_WA, _WB, _WC):
        if best_dir == -1.0 and choch_bull == 1.0:
            out["ew_w5_exhaustion"] = 1.0
            score += W_CHOCH_WAVE5
        elif best_dir == 1.0 and choch_bear == 1.0:
            out["ew_w5_exhaustion"] = 1.0
            score += W_CHOCH_WAVE5

    # 7. Correction at FVG: EW correction wave at FVG zone
    if best_wave in (_WA, _WB, _WC) and fvg_type != 0.0:
        # Bullish FVG during down correction = potential bounce zone
        if fvg_type == 1.0 and best_dir == -1.0:
            out["ew_correction_at_fvg"] = 1.0
            score += W_FVG_CORRECTION
        elif fvg_type == -1.0 and best_dir == 1.0:
            out["ew_correction_at_fvg"] = 1.0
            score += W_FVG_CORRECTION

    # Clamp score to 0-1
    out["confluence_score"] = min(1.0, max(0.0, score))

    # Determine overall direction: if score > 0.3, use best degree direction
    if score >= 0.3:
        out["confluence_direction"] = best_dir
    else:
        out["confluence_direction"] = 0.0

    return out


# ─── Single-bar compute ────────────────────────────────────────────────

def smc_ew_at(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, float]:
    """Compute SMC+EW confluence at the last bar.

    Params:
        smc_params: dict — passed to SMC indicator
        ew_params: dict — passed to EW indicator
    """
    smc_params = params.get("smc_params", {})
    ew_params = params.get("ew_params", {})

    try:
        smc = smc_structure_at(df, smc_params)
        ew = elliott_at(df, ew_params)
        return _compute_confluence(smc, ew)
    except Exception as e:
        logger.warning(f"SMC_EW confluence computation failed: {e}")
        return dict(SMC_EW_EMPTY)


# ─── Full-series compute ───────────────────────────────────────────────

def smc_ew_series(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, list[float | None]]:
    """Compute SMC+EW confluence over all bars."""
    n = len(df)
    empty = {k: [None] * n for k in SMC_EW_EMPTY}

    if n < 10:
        return empty

    smc_params = params.get("smc_params", {})
    ew_params = params.get("ew_params", {})

    try:
        smc_data = smc_structure_series(df, smc_params)
        ew_data = elliott_series(df, ew_params)

        result: dict[str, list[float | None]] = {k: [None] * n for k in SMC_EW_EMPTY}

        for i in range(n):
            # Build per-bar dicts from series data
            smc_bar = {k: (v[i] if v[i] is not None else 0.0) for k, v in smc_data.items()
                       if k in SMC_EMPTY and i < len(v)}
            ew_bar = {k: (v[i] if v[i] is not None else 0.0) for k, v in ew_data.items()
                      if k in ELLIOTT_EMPTY and i < len(v)}

            if smc_bar and ew_bar:
                confluence = _compute_confluence(smc_bar, ew_bar)
                for k, v in confluence.items():
                    if k in result:
                        result[k][i] = v

        return result
    except Exception as e:
        logger.warning(f"SMC_EW series computation failed: {e}")
        return empty
