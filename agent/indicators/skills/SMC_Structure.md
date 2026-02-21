# SMC_Structure — Smart Money Concepts: Market Structure

## 1. Overview

The SMC_Structure indicator identifies institutional market structure by tracking swing highs/lows (with alternation rule), break of structure (BOS), change of character (CHoCH), and deriving premium/discount zones with optimal trade entry (OTE) levels. It is the foundational directional bias indicator for any SMC-based playbook.

**Indicator ID pattern:** `<timeframe>_smc_structure` (e.g., `h4_smc_structure`, `m15_smc_structure`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `trend` | float | Current structure direction: `1` = bullish, `-1` = bearish, `0` = undefined |
| `strong_high` | float | Protected high — CHoCH trigger in bearish trend. If broken, trend reverses to bullish. |
| `strong_low` | float | Protected low — CHoCH trigger in bullish trend. If broken, trend reverses to bearish. |
| `ref_high` | float | Reference high (last HH) — BOS trigger in bullish trend |
| `ref_low` | float | Reference low (last LL) — BOS trigger in bearish trend |
| `equilibrium` | float | 50% midpoint of the current structural range |
| `ote_top` | float | Top of OTE zone (Fib 0.618 retracement) |
| `ote_bottom` | float | Bottom of OTE zone (Fib 0.786 retracement) |
| `zone` | float | `+1` = premium (price above equilibrium), `-1` = discount (below equilibrium) |
| `bos_bull` | float | `1` if a bullish BOS fired on this bar, else `0` |
| `bos_bear` | float | `1` if a bearish BOS fired on this bar, else `0` |
| `choch_bull` | float | `1` if a bullish CHoCH fired on this bar, else `0` |
| `choch_bear` | float | `1` if a bearish CHoCH fired on this bar, else `0` |

## 2. When to Use

- **Primary directional bias** on any timeframe — this is the "north star" for SMC playbooks.
- **Multi-timeframe alignment** — use H4 for bias, M15/M5 for entry timing.
- **Invalidation management** — strong_low/strong_high define where your thesis is wrong.
- **Entry zone identification** — OTE and discount/premium zones for high-R entries.
- **Event detection** — bos_bull/bos_bear and choch_bull/choch_bear fire on the exact bar of a structural event.
- Use this indicator on **every SMC playbook** as the structural backbone.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `swing_length` | 5 | 3–50 | Bars on each side to confirm a swing high/low. Lower = more swings, noisier. Higher = fewer swings, smoother. |
| `break_mode` | "Wick" | "Wick" or "Close" | Whether structure breaks require a wick or close beyond the level. "Wick" is more sensitive. |

**Advanced parameters (rarely changed):**

| Parameter | Default | Description |
|---|---|---|
| `max_swings` | 200 | Maximum swing points to track in memory |
| `eq_atr_mult` | 0.1 | ATR multiplier for equilibrium zone threshold |
| `eq_min_touches` | 2 | Minimum touches to confirm an equilibrium level |

**XAUUSD recommended:** `swing_length: 5`, `break_mode: "Wick"` — defaults work well. For H4, consider `swing_length: 8` to filter noise swings.

## 4. Key Patterns & Setups

### 4.1 Break of Structure (BOS) — Trend Continuation

BOS occurs when price breaks the reference high (bullish) or reference low (bearish), confirming trend continuation. Detected via `bos_bull` and `bos_bear` event flags.

**Buy after bullish BOS — wait for pullback to OTE:**
```json
{
  "phase": "wait_for_bos",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "ind.h4_smc_structure.bos_bull", "operator": "==", "right": "1", "description": "BOS confirmed — ref_high broken"}
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

### 4.2 Change of Character (CHoCH) — Trend Reversal

CHoCH occurs when price breaks the strong level (strong_low in bullish trend → bearish CHoCH, strong_high in bearish trend → bullish CHoCH). Detected via `choch_bull` and `choch_bear` event flags.

**Detect bearish CHoCH (was bullish, now bearish):**
```json
{
  "phase": "detect_choch",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.choch_bear", "operator": "==", "right": "1", "description": "Bearish CHoCH fired — strong_low was broken"}
    ]
  },
  "transitions": [{"target": "wait_for_sell_entry"}]
}
```

**Alternative — detect via trend flip:**
```json
{
  "phase": "detect_choch_alt",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "prev.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Was bullish"},
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Now bearish — CHoCH confirmed"}
    ]
  },
  "transitions": [{"target": "wait_for_sell_entry"}]
}
```

### 4.3 Premium/Discount Zone Trading

The `zone` field directly tells you if price is in premium (+1) or discount (-1). Price above equilibrium = **premium zone** (look for sells). Price below equilibrium = **discount zone** (look for buys).

**Buy in discount zone:**
```json
{
  "phase": "discount_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish bias"},
      {"left": "ind.h4_smc_structure.zone", "operator": "==", "right": "-1", "description": "Price in discount zone"}
    ]
  }
}
```

### 4.4 OTE Zone Entry (Optimal Trade Entry)

The OTE zone sits between the 61.8% and 78.6% Fibonacci retracement of the current structural range. This is the highest-probability entry zone in SMC.

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

**H4 bullish + M15 bullish alignment in discount:**
```json
{
  "phase": "mtf_alignment",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "H4 bullish"},
      {"left": "ind.m15_smc_structure.trend", "operator": "==", "right": "1", "description": "M15 aligns bullish"},
      {"left": "ind.h4_smc_structure.zone", "operator": "==", "right": "-1", "description": "H4 discount zone"}
    ]
  }
}
```

## 5. Combinations

| Combine With | Purpose | Role of SMC_Structure |
|---|---|---|
| OB_FVG | Entry precision | SMC provides bias + zone; OB/FVG provides exact entry |
| NW_Envelope | Mean reversion filter | SMC provides trend; NW confirms overextension |
| NW_RQ_Kernel | Trend confirmation | Kernel smoothes trend; double confirmation reduces false signals |
| TPO | Institutional levels | SMC provides structure; TPO provides POC/VA consensus levels |
| RSI | Momentum confirmation | SMC provides structure; RSI confirms divergence at key levels |
| ATR | Risk management | SMC provides SL level (strong_low/high); ATR sizes position |

**Best combination:** SMC_Structure (H4) + OB_FVG (M15) + ATR — the core institutional playbook.

## 6. Position Management

### Stop Loss Placement
- **Bullish trades:** SL below `strong_low` — this is the invalidation level. If strong_low breaks, a bearish CHoCH fires and your bullish thesis is wrong.
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
- **TP1:** Reference level in the trend direction (ref_high for buys, ref_low for sells)
- **TP2:** Next structure level or liquidity pool

### Trail Stop
- Move SL to breakeven after price clears equilibrium.
- Trail using M15 structure levels as price creates new swings.

## 7. Pitfalls

1. **Trading against HTF structure.** Never take M15 buys when H4 trend is bearish. Always align with higher timeframe.
2. **Entering on the first CHoCH.** A single CHoCH is not confirmation — wait for a pullback and BOS in the new direction before entering.
3. **Ignoring strong_low/strong_high.** These are your invalidation levels. If price breaks them, exit immediately — a CHoCH has fired and your thesis is wrong.
4. **Using too-small swing_length.** Small values detect every minor swing and generate false structure breaks. On H4 XAUUSD, keep `swing_length >= 5`.
5. **OTE in ranging markets.** OTE works best in trending conditions. In a range, equilibrium and OTE levels become meaningless noise.
6. **Not accounting for spread.** XAUUSD spreads widen during news. Your BOS detection may trigger on a spread spike, not real structure break. Use `break_mode: "Close"` during volatile sessions.

## 8. XAUUSD-Specific Notes

- **Volatility:** Gold averages 150–300 pip daily ranges. Default `swing_length: 5` works well; increase to 8 on H4 to filter noise.
- **Session behavior:** London open (07:00–08:00 UTC) and NY open (13:00–14:00 UTC) produce the most reliable structure breaks. Asian session structure breaks frequently fail.
- **Strong lows/highs:** Gold strongly respects weekly/daily strong lows and highs. These levels act as major liquidity pools.
- **CHoCH reliability:** CHoCH on H4 gold is highly reliable for trend changes. M15 CHoCH should be used only for entries, not bias changes.
- **BOS characteristics:** Gold tends to produce aggressive BOS moves (20–50 pips in minutes). Set entries at OTE rather than chasing the break.
- **Equilibrium as magnet:** Gold frequently returns to equilibrium before continuing. Use this for re-entry after missing the initial move.
- **News events:** NFP, FOMC, CPI — structure breaks during these events are unreliable. Either use `break_mode: "Close"` or pause the playbook 30 min before/after.
