# SMC_Structure — Smart Money Concepts: Market Structure

## 1. Overview

The SMC_Structure indicator identifies institutional market structure by tracking swing highs/lows, break of structure (BOS), change of character (CHOCH), and deriving premium/discount zones with optimal trade entry (OTE) levels. It is the foundational directional bias indicator for any SMC-based playbook.

**Indicator ID pattern:** `<timeframe>_smc_structure` (e.g., `h4_smc_structure`, `m15_smc_structure`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `swing_high` | float | Most recent confirmed swing high price |
| `swing_low` | float | Most recent confirmed swing low price |
| `trend` | int | Current structure direction: `1` = bullish, `-1` = bearish |
| `strong_low` | float | Protected low — invalidation level for bullish bias |
| `strong_high` | float | Protected high — invalidation level for bearish bias |
| `ref_high` | float | Reference high used to detect next BOS/CHOCH |
| `ref_low` | float | Reference low used to detect next BOS/CHOCH |
| `equilibrium` | float | Midpoint of current range: `(swing_high + swing_low) / 2` |
| `ote_top` | float | Top of OTE zone (61.8% retracement) |
| `ote_bottom` | float | Bottom of OTE zone (78.6% retracement) |
| `swing_high_clr` | int | `1` if swing high was cleared (broken) on current bar, else `0` |
| `swing_low_clr` | int | `1` if swing low was cleared (broken) on current bar, else `0` |

## 2. When to Use

- **Primary directional bias** on any timeframe — this is the "north star" for SMC playbooks.
- **Multi-timeframe alignment** — use H4 for bias, M15/M5 for entry timing.
- **Invalidation management** — strong_low/strong_high define where your thesis is wrong.
- **Entry zone identification** — OTE and discount/premium zones for high-R entries.
- Use this indicator on **every SMC playbook** as the structural backbone.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `swing_length` | 10 | 5–50 | Lookback bars for swing detection. Lower = more swings, noisier. Higher = fewer swings, smoother. |
| `atr_length` | 14 | 7–50 | ATR period for filtering insignificant swings |
| `atr_multiplier` | 0.5 | 0.1–2.0 | Minimum swing size as ATR multiple. Increase for XAUUSD to filter noise. |

**XAUUSD recommended:** `swing_length: 10`, `atr_multiplier: 0.7` (gold has wide swings; filtering small ones improves structure quality).

## 4. Key Patterns & Setups

### 4.1 Break of Structure (BOS) — Trend Continuation

BOS occurs when price breaks the most recent swing high (in uptrend) or swing low (in downtrend), confirming trend continuation.

**Detection:** `trend` remains the same value, but `swing_high_clr == 1` (bullish) or `swing_low_clr == 1` (bearish).

**Buy after bullish BOS — wait for pullback to OTE:**
```json
{
  "phase": "wait_for_bos",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "ind.h4_smc_structure.swing_high_clr", "operator": "==", "right": "1", "description": "BOS confirmed — swing high broken"}
    ]
  },
  "transitions": [{"target": "wait_for_pullback"}]
}
```

**Wait for pullback into OTE zone:**
```json
{
  "phase": "wait_for_pullback",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "Price entered OTE zone"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_smc_structure.ote_bottom", "description": "Price above OTE bottom"}
    ]
  },
  "transitions": [{"target": "entry"}]
}
```

### 4.2 Change of Character (CHOCH) — Trend Reversal

CHOCH occurs when the trend field flips from `1` to `-1` or vice versa. This signals a potential reversal.

**Detect bearish CHOCH (was bullish, now bearish):**
```json
{
  "phase": "detect_choch",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "prev.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Was bullish"},
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Now bearish — CHOCH confirmed"}
    ]
  },
  "transitions": [{"target": "wait_for_sell_entry"}]
}
```

### 4.3 Premium/Discount Zone Trading

Price above equilibrium = **premium zone** (look for sells). Price below equilibrium = **discount zone** (look for buys).

**Buy in discount zone:**
```json
{
  "phase": "discount_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish bias"},
      {"left": "_price", "operator": "<", "right": "ind.h4_smc_structure.equilibrium", "description": "Price in discount zone"}
    ]
  }
}
```

### 4.4 OTE Zone Entry (Optimal Trade Entry)

The OTE zone sits between the 61.8% and 78.6% Fibonacci retracement of the current swing. This is the highest-probability entry zone in SMC.

**Buy in OTE during bullish structure:**
```json
{
  "phase": "ote_entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "Below OTE top (61.8%)"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_smc_structure.ote_bottom", "description": "Above OTE bottom (78.6%)"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.5 Multi-TF Structure Alignment

Use H4 for directional bias, M15 for entry structure alignment.

**H4 bullish + M15 bullish alignment:**
```json
{
  "phase": "mtf_alignment",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "H4 bullish"},
      {"left": "ind.m15_smc_structure.trend", "operator": "==", "right": "1", "description": "M15 aligns bullish"},
      {"left": "_price", "operator": "<", "right": "ind.h4_smc_structure.equilibrium", "description": "H4 discount zone"}
    ]
  }
}
```

## 5. Combinations

| Combine With | Purpose | Role of SMC_Structure |
|---|---|---|
| OB_FVG | Entry precision | SMC provides bias + zone; OB/FVG provides exact entry |
| NW_Envelope | Mean reversion filter | SMC provides trend; NW confirms overextension |
| RSI | Momentum confirmation | SMC provides structure; RSI confirms divergence at key levels |
| ATR | Risk management | SMC provides SL level (strong_low/high); ATR sizes position |
| EMA/SMA | Trend confirmation | EMA confirms SMC trend direction for added confidence |

**Best combination:** SMC_Structure (H4) + OB_FVG (M15) + ATR — the core institutional playbook.

## 6. Position Management

### Stop Loss Placement
- **Bullish trades:** SL below `strong_low` — this is the invalidation level. If strong_low breaks, your bullish thesis is wrong.
- **Bearish trades:** SL above `strong_high`.

```json
{
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_smc_structure.strong_low",
    "offset": "-0.5",
    "description": "SL below strong low with 0.50 buffer"
  }
}
```

### Take Profit
- **TP1:** Opposing swing (swing_high for buys, swing_low for sells)
- **TP2:** Next structure level or liquidity pool

### Trail Stop
- Move SL to breakeven after price clears equilibrium.
- Trail using M15 swing lows (for buys) as price creates new structure.

## 7. Pitfalls

1. **Trading against HTF structure.** Never take M15 buys when H4 trend is bearish. Always align with higher timeframe.
2. **Entering on the first CHOCH.** A single CHOCH is not confirmation — wait for a pullback and BOS in the new direction before entering.
3. **Ignoring strong_low/strong_high.** These are your invalidation levels. If price breaks them, exit immediately — do not hope.
4. **Using too-small swing_length.** Small values detect every minor swing and generate false structure breaks. On H4 XAUUSD, keep `swing_length >= 8`.
5. **OTE in ranging markets.** OTE works best in trending conditions. In a range, equilibrium and OTE levels become meaningless noise.
6. **Not accounting for spread.** XAUUSD spreads widen during news. Your BOS detection may trigger on a spread spike, not real structure break.

## 8. XAUUSD-Specific Notes

- **Volatility:** Gold averages 150–300 pip daily ranges. Use `atr_multiplier: 0.7` or higher to filter noise swings.
- **Session behavior:** London open (07:00–08:00 UTC) and NY open (13:00–14:00 UTC) produce the most reliable structure breaks. Asian session structure breaks frequently fail.
- **Strong lows/highs:** Gold strongly respects weekly/daily strong lows and highs. These levels act as major liquidity pools.
- **CHOCH reliability:** CHOCH on H4 gold is highly reliable for trend changes. M15 CHOCH should be used only for entries, not bias changes.
- **BOS characteristics:** Gold tends to produce aggressive BOS moves (20–50 pips in minutes). Set entries at OTE rather than chasing the break.
- **Equilibrium as magnet:** Gold frequently returns to equilibrium before continuing. Use this for re-entry after missing the initial move.
- **News events:** NFP, FOMC, CPI — structure breaks during these events are unreliable. Either widen filters or pause the playbook 30 min before/after.
