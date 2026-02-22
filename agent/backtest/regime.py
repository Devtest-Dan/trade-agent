"""Market regime detection — classify bars as trending/ranging/volatile.

Uses ADX for trend strength and ATR percentile for volatility classification.
Each bar gets a regime label: "trending", "ranging", "volatile", or "quiet".
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pandas_ta as ta

from agent.models.market import Bar


# Regime labels
TRENDING = "trending"
RANGING = "ranging"
VOLATILE = "volatile"
QUIET = "quiet"


@dataclass
class RegimeStats:
    """Per-regime trade statistics."""
    regime: str
    total: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    total_pnl: float = 0.0


def classify_regimes(
    bars: list[Bar],
    adx_period: int = 14,
    atr_period: int = 14,
    adx_trend_threshold: float = 25.0,
    atr_volatile_percentile: float = 75.0,
    atr_quiet_percentile: float = 25.0,
) -> list[str]:
    """Classify each bar into a market regime.

    Logic:
    - ADX > threshold → "trending" (strong directional move)
    - ADX <= threshold AND ATR > 75th percentile → "volatile" (choppy, wide range)
    - ADX <= threshold AND ATR < 25th percentile → "quiet" (low activity)
    - Otherwise → "ranging" (normal, no strong trend or volatility)

    Returns list of regime labels, same length as bars. First ~adx_period bars
    are labeled "ranging" by default.
    """
    if len(bars) < adx_period + 5:
        return [RANGING] * len(bars)

    df = pd.DataFrame({
        "high": [b.high for b in bars],
        "low": [b.low for b in bars],
        "close": [b.close for b in bars],
    })

    # Compute ADX and ATR
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=adx_period)
    atr_series = ta.atr(df["high"], df["low"], df["close"], length=atr_period)

    if adx_df is None or atr_series is None:
        return [RANGING] * len(bars)

    adx_col = f"ADX_{adx_period}"
    adx_values = adx_df[adx_col].values if adx_col in adx_df.columns else np.full(len(bars), 0.0)
    atr_values = atr_series.values

    # Compute ATR percentiles from valid (non-NaN) values
    valid_atr = atr_values[~np.isnan(atr_values)]
    if len(valid_atr) < 10:
        return [RANGING] * len(bars)

    atr_p75 = np.percentile(valid_atr, atr_volatile_percentile)
    atr_p25 = np.percentile(valid_atr, atr_quiet_percentile)

    regimes: list[str] = []
    for i in range(len(bars)):
        adx = adx_values[i] if i < len(adx_values) and not np.isnan(adx_values[i]) else 0.0
        atr = atr_values[i] if i < len(atr_values) and not np.isnan(atr_values[i]) else 0.0

        if adx > adx_trend_threshold:
            regimes.append(TRENDING)
        elif atr > atr_p75:
            regimes.append(VOLATILE)
        elif atr < atr_p25:
            regimes.append(QUIET)
        else:
            regimes.append(RANGING)

    return regimes


def compute_regime_stats(
    trades: list,
    regimes_at_entry: list[str],
) -> list[RegimeStats]:
    """Compute per-regime trade statistics.

    Args:
        trades: BacktestTrade objects
        regimes_at_entry: regime label for each trade (same order)
    """
    stats_map: dict[str, list] = {}
    for trade, regime in zip(trades, regimes_at_entry):
        stats_map.setdefault(regime, []).append(trade)

    results = []
    for regime in [TRENDING, RANGING, VOLATILE, QUIET]:
        trade_list = stats_map.get(regime, [])
        if not trade_list:
            results.append(RegimeStats(regime=regime))
            continue

        wins = len([t for t in trade_list if t.outcome == "win"])
        pnls = [t.pnl for t in trade_list]
        results.append(RegimeStats(
            regime=regime,
            total=len(trade_list),
            wins=wins,
            losses=len([t for t in trade_list if t.outcome == "loss"]),
            win_rate=round(wins / len(trade_list) * 100, 1),
            avg_pnl=round(statistics.mean(pnls), 2),
            total_pnl=round(sum(pnls), 2),
        ))

    return results
