# TPO — Time Price Opportunity (Market Profile)

## 1. Overview

The TPO indicator builds a rolling-window price histogram showing how much time price spent at each level. It reveals the **Point of Control** (highest-activity price), **Value Area** (where 70% of activity occurred), and key support/resistance levels. These levels represent institutional consensus and act as magnets for price action. Critical for SMC-based strategies.

**Indicator ID pattern:** `<timeframe>_tpo` (e.g., `h4_tpo`, `m15_tpo`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `poc` | float | Point of Control — price level with the most time spent (highest TPO count) |
| `vah` | float | Value Area High — upper boundary of the 70% activity zone |
| `val` | float | Value Area Low — lower boundary of the 70% activity zone |

### Derived Values

- **Value Area Width:** `vah - val` — wider = more distributed activity, narrower = concentrated/balanced
- **Price vs POC:** `_price - ind.h4_tpo.poc` — positive = above POC (bullish positioning), negative = below
- **Price within VA:** `_price >= ind.h4_tpo.val AND _price <= ind.h4_tpo.vah` — balanced / fair value

## 2. When to Use

- **Support/resistance identification** — POC, VAH, and VAL act as key institutional levels.
- **Fair value assessment** — price within the Value Area is at "fair value"; outside is overextended.
- **Breakout confirmation** — price breaking above VAH or below VAL with conviction signals directional moves.
- **Mean reversion** — price outside the Value Area tends to revert to the POC.
- **Range vs trend detection** — narrow Value Area = balanced/ranging; wide = trending/volatile.
- **Entry zone confluence** — combine with SMC/OB_FVG for high-probability entries at POC or VA boundaries.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `lookback` | 50 | 20–200 | Number of bars in the profile window. Higher = smoother, more stable levels. Lower = more responsive. |
| `num_bins` | 24 | 10–50 | Price histogram resolution. Higher = more precise levels but may overfit. |
| `value_area_pct` | 70.0 | 50.0–90.0 | Percentage of TPOs included in Value Area. Standard is 70%. |

**XAUUSD recommended:** `lookback: 50`, `num_bins: 24`, `value_area_pct: 70` — defaults work well on H1/H4 gold.

## 4. Key Patterns & Setups

### 4.1 POC as Support/Resistance

The POC is the price where the market spent the most time — it represents institutional consensus. Price tends to be attracted to the POC.

**Buy at POC support in uptrend:**
```json
{
  "phase": "poc_support",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_tpo.poc * 1.0003", "description": "Price at or near POC"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_tpo.poc * 0.9997", "description": "Within POC zone (±3 pips)"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Sell at POC resistance in downtrend:**
```json
{
  "phase": "poc_resistance",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Bearish structure"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_tpo.poc * 0.9997", "description": "Price at or near POC"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_tpo.poc * 1.0003", "description": "Within POC zone"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

### 4.2 Value Area Breakout

Price breaking above VAH suggests buyers are in control; breaking below VAL suggests sellers dominate.

**Buy on VAH breakout (bullish):**
```json
{
  "phase": "vah_breakout",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish bias"},
      {"left": "_price", "operator": ">", "right": "ind.h4_tpo.vah", "description": "Price broke above Value Area High"},
      {"left": "ind.h4_nw_rq_kernel.is_bullish", "operator": "==", "right": "1", "description": "Kernel confirms bullish momentum"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Sell on VAL breakdown (bearish):**
```json
{
  "phase": "val_breakdown",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Bearish bias"},
      {"left": "_price", "operator": "<", "right": "ind.h4_tpo.val", "description": "Price broke below Value Area Low"},
      {"left": "ind.h4_nw_rq_kernel.is_bearish", "operator": "==", "right": "1", "description": "Kernel confirms bearish momentum"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

### 4.3 Mean Reversion to POC

When price moves outside the Value Area, it tends to revert back to the POC. This is especially effective in ranging markets.

**Fade above VAH — sell back to POC:**
```json
{
  "phase": "fade_above_vah",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">", "right": "ind.h4_tpo.vah", "description": "Price above Value Area — overextended"},
      {"left": "ind.h4_nw_envelope.nw_bearish", "operator": "==", "right": "1", "description": "Kernel turning bearish — reversal starting"},
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Structure confirms bearish"}
    ]
  },
  "transitions": [{"target": "execute_sell", "take_profit": "ind.h4_tpo.poc"}]
}
```

### 4.4 Value Area Rotation (Range Trading)

When the market is balanced (narrow VA width), trade the rotation between VAH and VAL.

**Buy at VAL, target VAH:**
```json
{
  "phase": "va_rotation_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": "<=", "right": "ind.h1_tpo.val * 1.0002", "description": "Price at Value Area Low"},
      {"left": "_price", "operator": ">=", "right": "ind.h1_tpo.val * 0.9998", "description": "Within VAL zone"}
    ]
  },
  "transitions": [{"target": "execute_buy", "take_profit": "ind.h1_tpo.vah"}]
}
```

### 4.5 POC + OB Confluence

When a POC aligns with an order block, the level has double institutional significance.

**High-probability buy — POC at bullish OB:**
```json
{
  "phase": "poc_ob_confluence",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "1", "description": "Bullish order block present"},
      {"left": "ind.h4_tpo.poc", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "POC within OB zone"},
      {"left": "ind.h4_tpo.poc", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "POC aligns with OB"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price entering the zone"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

## 5. Combinations

| Combine With | Purpose | Role of TPO |
|---|---|---|
| SMC_Structure | Institutional levels + structure | TPO provides consensus levels; SMC provides directional bias |
| OB_FVG | Entry confluence | POC at OB = high-probability zone; VAH/VAL as secondary S/R |
| NW_Envelope | Mean reversion zones | TPO defines fair value; NW confirms overextension |
| NW_RQ_Kernel | Trend + levels | Kernel provides trend direction; TPO provides key levels |
| RSI | Momentum at levels | Enter at POC/VAH/VAL only when RSI confirms momentum |
| ATR | Risk sizing | VA width gives range context; ATR sizes position |

**Best combination:** TPO (levels) + SMC_Structure (bias) + OB_FVG (entry precision) — institutional-grade setup.

## 6. Position Management

### Stop Loss
- **POC entries:** SL beyond the nearest VA boundary. For buys at POC, SL below VAL.
- **VA boundary entries:** SL 1-2 ATR beyond the VA boundary.
- **Breakout trades:** SL back inside the Value Area (POC level).

```json
{
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_tpo.val",
    "offset": "-1.0",
    "description": "SL below Value Area Low with $1 buffer"
  }
}
```

### Take Profit
- **From VAL:** Target POC (TP1), then VAH (TP2).
- **From POC:** Target VAH (buys) or VAL (sells).
- **Breakout above VAH:** Target POC + (VAH - POC) as measured move.

### Trailing
- Trail using POC as the stop reference. As the profile shifts, POC moves with it.

## 7. Pitfalls

1. **Trading POC in a strong trend.** In a trending market, POC lags behind price. Don't expect price to return to POC during a strong move — use POC only when structure supports mean reversion.
2. **Ignoring VA width.** A very narrow Value Area suggests an upcoming breakout. Don't fade the boundaries — trade the breakout instead.
3. **Too-small lookback.** With `lookback < 20`, the profile becomes noisy and POC jumps around. Use at least 30-50 bars for stable levels.
4. **Confusing TPO with volume profile.** TPO measures time at price; Volume Profile measures volume at price. They usually agree but can diverge during high-volume spike bars.
5. **Over-reliance on exact levels.** POC/VAH/VAL are zones, not exact prices. Use a buffer (2-5 pips for XAUUSD) around each level.
6. **Stale profiles.** After major news events, the historical TPO profile becomes less relevant. Consider reducing `lookback` temporarily or waiting for a new profile to develop.

## 8. XAUUSD-Specific Notes

- **POC as magnet.** Gold respects the POC exceptionally well. Intraday price action on H1 frequently tests the POC 3-5 times before making a directional move.
- **VAH/VAL as session levels.** On H1 gold, VAH and VAL often align with session highs/lows (London open range, NY range).
- **Value Area width.** Typical H4 gold VA width is $15-$40. Below $10 suggests a squeeze; above $50 suggests trending/volatile conditions.
- **POC zone buffer.** For XAUUSD, use a 2.5-pip (±$0.25) zone around the POC for entries. Gold's spread can cause false touches at the exact POC level.
- **Session-specific behavior.** Asian session profiles tend to be narrow (balanced). London/NY profiles tend to be wider (directional). Use Asian session POC as the key level for London open entries.
- **News events.** NFP/FOMC can shift the POC dramatically in one bar. After major news, wait 3-5 bars for the profile to stabilize before using TPO levels.
- **Weekly POC.** Using `lookback: 120` on H1 approximates a weekly profile. The weekly POC is a very strong institutional level on gold.
