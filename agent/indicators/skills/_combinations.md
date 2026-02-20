# Indicator Combinations Guide

## 1. Overview

This document teaches how to combine indicators into effective playbooks. No single indicator provides a complete trading edge — combinations create layered strategies where each indicator serves a specific role: **filter** (directional bias), **trigger** (entry signal), **confirmation** (additional validation), or **management** (stop/target/sizing).

The playbook state machine follows a standard phase pattern:
```
idle → wait (filter conditions) → entry (trigger + confirmation) → in_position (management) → idle
```

Every combination below follows this pattern. The key decision is: **which indicator goes in which phase?**

### Indicator Role Taxonomy

| Role | Purpose | Phase | Examples |
|---|---|---|---|
| **Filter** | Establishes directional bias, eliminates wrong-side trades | `idle → wait` | SMC_Structure.trend, EMA direction, ADX threshold, NW kernel direction |
| **Trigger** | Defines exact entry condition | `wait → entry` | OB zone touch, FVG fill, RSI cross, envelope touch, MACD cross |
| **Confirmation** | Additional validation to reduce false triggers | Within `entry` phase | RSI divergence, volume spike, candle pattern, second TF alignment |
| **Management** | Sizes positions, sets SL/TP, trails stops | `in_position` | ATR for sizing, OB/envelope for SL, structure levels for TP |

---

## 2. Combination 1: Trend + Momentum

**Indicators:** EMA/SMA (trend) + RSI/Stochastic/MACD (momentum)

### When to Use
- Classic directional trading on any instrument.
- When you want a simple, robust system that works across markets.
- When you do not have access to SMC indicators or want a traditional approach.
- Good for beginners and as a baseline before adding SMC complexity.

### Roles
| Indicator | Role | Purpose |
|---|---|---|
| EMA 50/200 | Filter | Establishes trend direction (price above EMA 50 = bullish) |
| RSI 14 | Trigger | Identifies pullback completion (RSI dips below 40 then crosses above in uptrend) |
| MACD | Confirmation | Histogram turning positive confirms momentum shift |
| ATR | Management | Position sizing and stop loss distance |

### Phase Design Pattern

```
idle: EMA direction check → wait
wait: Price pulls back toward EMA → entry
entry: RSI/MACD confirm momentum → execute
in_position: Trail with EMA, manage with ATR → idle
```

### Playbook JSON

**Phase 1 — Idle (check trend filter):**
```json
{
  "phase": "idle",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">", "right": "ind.h4_ema_50.value", "description": "Price above EMA 50 — bullish filter"},
      {"left": "ind.h4_ema_50.value", "operator": ">", "right": "ind.h4_ema_200.value", "description": "EMA 50 above EMA 200 — trend confirmed"}
    ]
  },
  "transitions": [{"target": "wait"}]
}
```

**Phase 2 — Wait (pullback detection):**
```json
{
  "phase": "wait",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_rsi.value", "operator": "<", "right": "40", "description": "RSI pulled back below 40 — oversold in uptrend"},
      {"left": "_price", "operator": ">", "right": "ind.h4_ema_200.value", "description": "Still above EMA 200 — not a trend break"}
    ]
  },
  "transitions": [{"target": "entry"}]
}
```

**Phase 3 — Entry (momentum confirmation):**
```json
{
  "phase": "entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_rsi.value", "operator": ">", "right": "45", "description": "RSI recovering — momentum returning"},
      {"left": "prev.m15_rsi.value", "operator": "<", "right": "45", "description": "RSI just crossed above 45 — fresh signal"},
      {"left": "ind.m15_macd.histogram", "operator": ">", "right": "0", "description": "MACD histogram positive — momentum confirmed"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Phase 4 — In Position (management):**
```json
{
  "phase": "in_position",
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_ema_200.value",
    "offset": "-2.0",
    "description": "SL below EMA 200 with buffer"
  },
  "take_profit": {
    "type": "expression",
    "value": "var.entry_price + ind.h4_atr.value * 3",
    "description": "TP at 3x ATR from entry"
  },
  "exit_conditions": {
    "type": "OR",
    "rules": [
      {"left": "_price", "operator": "<", "right": "ind.h4_ema_50.value", "description": "Price broke below EMA 50 — trend weakening"},
      {"left": "ind.m15_rsi.value", "operator": ">", "right": "80", "description": "RSI extremely overbought — take profit"}
    ]
  }
}
```

### XAUUSD Tuning
- Use EMA 50 and EMA 200 on H4. Gold respects these levels well.
- RSI pullback threshold: use 35 instead of 40 for XAUUSD (gold trends harder, so RSI stays elevated longer).
- MACD parameters: default (12, 26, 9) work well. Consider (8, 21, 5) for faster signals on M15 gold.

---

## 3. Combination 2: Structure + Entry (SMC Core)

**Indicators:** SMC_Structure (bias) + OB_FVG (entry) + RSI (timing)

### When to Use
- Institutional/Smart Money trading approach.
- When you want the highest probability entries with clear invalidation.
- XAUUSD — this is the most effective combination for gold.
- When you understand and want to trade market structure.

### Roles
| Indicator | Role | Purpose |
|---|---|---|
| SMC_Structure (H4) | Filter | Trend direction, premium/discount zones, strong_low/high invalidation |
| OB_FVG (M15) | Trigger | Exact entry at order block or FVG zone |
| RSI (M15) | Confirmation | Oversold/overbought confirmation at the entry zone |
| SMC_Structure | Management | Strong_low for SL, swing_high for TP |

### Phase Design Pattern

```
idle: H4 structure bullish + price in discount → wait
wait: M15 OB or FVG zone detected → entry
entry: RSI confirms oversold at zone → execute
in_position: SL at strong_low, TP at swing_high → idle
```

### Playbook JSON

**Phase 1 — Idle (structural bias):**
```json
{
  "phase": "idle",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "H4 structure is bullish"},
      {"left": "_price", "operator": "<", "right": "ind.h4_smc_structure.equilibrium", "description": "Price is in discount zone — good for buys"}
    ]
  },
  "transitions": [{"target": "wait"}]
}
```

**Phase 2 — Wait (entry zone detection):**
```json
{
  "phase": "wait",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "1", "description": "Bullish order block present on M15"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price entered the OB zone"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price within OB boundaries"}
    ]
  },
  "transitions": [{"target": "entry"}]
}
```

**Phase 3 — Entry (RSI confirmation):**
```json
{
  "phase": "entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_rsi.value", "operator": "<", "right": "35", "description": "RSI oversold — momentum supports buy"},
      {"left": "ind.m15_ob_fvg.combined_partial", "operator": "==", "right": "1", "description": "At least OB + FVG or OB + ZZ align — confluence"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Phase 4 — In Position:**
```json
{
  "phase": "in_position",
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_smc_structure.strong_low",
    "offset": "-1.0",
    "description": "SL below strong low — structural invalidation"
  },
  "take_profit": {
    "type": "indicator",
    "reference": "ind.h4_smc_structure.swing_high",
    "description": "TP at the next swing high"
  },
  "exit_conditions": {
    "type": "OR",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Structure flipped bearish — exit immediately"},
      {"left": "ind.m15_rsi.value", "operator": ">", "right": "80", "description": "RSI extreme overbought — consider partial TP"}
    ]
  }
}
```

### XAUUSD Tuning
- H4 SMC_Structure with `swing_length: 10`, `atr_multiplier: 0.7` for clean gold structure.
- M15 OB_FVG with `ob_strength: 4` to filter weak OBs on gold.
- RSI oversold at 35 (not 30) — gold RSI rarely hits 30 during trending pullbacks.
- Strong_low SL with $1.00 buffer — gold can wick $0.50 below strong lows.

---

## 4. Combination 3: Volatility + Trend

**Indicators:** ATR (volatility) + ADX (trend strength) + EMA (direction)

### When to Use
- When you want to trade only in strong trends and avoid choppy markets.
- Position sizing that adapts to market volatility.
- When you need a trend strength filter to prevent whipsaw entries.
- Works well on all timeframes and instruments.

### Roles
| Indicator | Role | Purpose |
|---|---|---|
| EMA 20/50 | Filter | Trend direction |
| ADX | Filter | Trend strength — only trade when ADX > 25 |
| ATR | Management | Dynamic position sizing and stop loss |

### Phase Design Pattern

```
idle: ADX > 25 (trending) + EMA direction → wait
wait: Price pullback to EMA 20 → entry
entry: ADX still > 25 + price bounces → execute
in_position: ATR-based SL/TP, exit when ADX < 20 → idle
```

### Playbook JSON

**Phase 1 — Idle (trend strength filter):**
```json
{
  "phase": "idle",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_adx.value", "operator": ">", "right": "25", "description": "ADX above 25 — market is trending"},
      {"left": "ind.h4_ema_20.value", "operator": ">", "right": "ind.h4_ema_50.value", "description": "EMA 20 above 50 — uptrend"},
      {"left": "_price", "operator": ">", "right": "ind.h4_ema_20.value", "description": "Price above EMA 20"}
    ]
  },
  "transitions": [{"target": "wait"}]
}
```

**Phase 2 — Wait (pullback):**
```json
{
  "phase": "wait",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": "<=", "right": "ind.h4_ema_20.value + ind.h4_atr.value * 0.3", "description": "Price pulled back near EMA 20 (within 0.3 ATR)"},
      {"left": "_price", "operator": ">", "right": "ind.h4_ema_50.value", "description": "Still above EMA 50 — pullback, not reversal"},
      {"left": "ind.h4_adx.value", "operator": ">", "right": "22", "description": "ADX still showing trend (allow slight dip during pullback)"}
    ]
  },
  "transitions": [{"target": "entry"}]
}
```

**Phase 3 — Entry:**
```json
{
  "phase": "entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">", "right": "ind.h4_ema_20.value", "description": "Price bounced above EMA 20 — pullback complete"},
      {"left": "prev._price", "operator": "<=", "right": "prev.h4_ema_20.value", "description": "Was at/below EMA 20 last bar — fresh bounce"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Phase 4 — In Position:**
```json
{
  "phase": "in_position",
  "stop_loss": {
    "type": "expression",
    "value": "var.entry_price - ind.h4_atr.value * 2",
    "description": "SL at 2x ATR below entry"
  },
  "take_profit": {
    "type": "expression",
    "value": "var.entry_price + ind.h4_atr.value * 4",
    "description": "TP at 4x ATR — 2:1 R:R minimum"
  },
  "exit_conditions": {
    "type": "OR",
    "rules": [
      {"left": "ind.h4_adx.value", "operator": "<", "right": "20", "description": "ADX dropped below 20 — trend died, exit"},
      {"left": "_price", "operator": "<", "right": "ind.h4_ema_50.value", "description": "Price below EMA 50 — trend broken"}
    ]
  }
}
```

### XAUUSD Tuning
- ADX threshold: 25 works well for H4 gold. Gold trends strongly when ADX > 30 — consider larger position sizes when ADX > 30.
- ATR SL multiplier: use 2.5x for XAUUSD (gold has wider swings; 2x ATR gets stopped out too easily).
- EMA periods: 20/50 on H4 is the sweet spot. On M15, use 21/55 for slightly smoother signals.
- Gold trends can persist for days with ADX > 40. Do not exit solely on high ADX — exit on ADX declining below 20.

---

## 5. Combination 4: Mean Reversion

**Indicators:** Bollinger Bands (volatility envelope) + RSI (momentum) + NW_Envelope (kernel regression)

### When to Use
- Range-bound or low-volatility markets.
- Counter-trend entries at statistically extreme price levels.
- Asian session trading (00:00-06:00 UTC) when gold oscillates.
- When ADX < 20 (no trend) — switch from trend-following to mean reversion.

### Roles
| Indicator | Role | Purpose |
|---|---|---|
| NW_Envelope | Filter + Trigger | Far envelope = extreme level, kernel direction = trend context |
| Bollinger Bands | Confirmation | BB outer band touch confirms statistical extreme (2 std devs) |
| RSI | Confirmation | RSI extreme (<25 or >75) confirms momentum exhaustion |

### Phase Design Pattern

```
idle: No trend (ADX < 20 or kernel flat) → wait
wait: Price reaches NW far envelope + BB outer band → entry
entry: RSI confirms extreme + kernel direction turning → execute
in_position: TP at kernel midline, SL beyond far envelope → idle
```

### Playbook JSON

**Phase 1 — Idle (range detection):**
```json
{
  "phase": "idle",
  "conditions": {
    "type": "OR",
    "rules": [
      {"left": "ind.h4_adx.value", "operator": "<", "right": "20", "description": "ADX below 20 — ranging market"},
      {
        "type": "AND",
        "rules": [
          {"left": "ind.h4_nw_envelope.nw_bullish", "operator": "==", "right": "0", "description": "Kernel not bullish"},
          {"left": "ind.h4_nw_envelope.nw_bearish", "operator": "==", "right": "0", "description": "Kernel not bearish — flat/ranging"}
        ]
      }
    ]
  },
  "transitions": [{"target": "wait"}]
}
```

**Phase 2 — Wait (extreme level):**
```json
{
  "phase": "wait_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": "<=", "right": "ind.h4_nw_envelope.lower_far", "description": "Price at NW lower far — extreme oversold"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_bollinger.lower", "description": "Price at/below Bollinger lower band — double extreme"}
    ]
  },
  "transitions": [{"target": "entry_buy"}]
}
```

**Phase 3 — Entry (momentum exhaustion):**
```json
{
  "phase": "entry_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_rsi.value", "operator": "<", "right": "25", "description": "RSI deeply oversold — momentum exhausted"},
      {"left": "ind.h4_nw_envelope.nw_bullish", "operator": "==", "right": "1", "description": "Kernel turning bullish — reversal beginning"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Phase 4 — In Position:**
```json
{
  "phase": "in_position",
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_nw_envelope.lower_far",
    "offset": "-3.0",
    "description": "SL beyond lower far envelope with $3 buffer"
  },
  "take_profit": {
    "type": "expression",
    "value": "(ind.h4_nw_envelope.upper_near + ind.h4_nw_envelope.lower_near) / 2",
    "description": "TP at kernel midline — mean reversion target"
  },
  "exit_conditions": {
    "type": "OR",
    "rules": [
      {"left": "_price", "operator": ">=", "right": "ind.h4_nw_envelope.upper_near", "description": "Price reached near envelope — partial TP zone"},
      {"left": "ind.m15_rsi.value", "operator": ">", "right": "70", "description": "RSI overbought — momentum fading on the reversion"}
    ]
  }
}
```

### XAUUSD Tuning
- Most effective during Asian session when gold ranges in $5-$15 bands.
- Use M15 timeframe for faster mean reversion signals during London/NY.
- NW far envelope + BB outer band alignment on gold has approximately 70% reversion rate.
- RSI threshold: use 25/75 (not 30/70) — gold at these extremes in ranging conditions almost always reverts.
- SL buffer: $3 beyond far envelope is appropriate for H4 gold. For M15, use $1.50.

---

## 6. Combination 5: Multi-TF Confluence

**Indicators:** H4 filters + M15 triggers (any indicator combination, layered across timeframes)

### When to Use
- Always. Multi-TF is not an optional enhancement — it is a fundamental principle.
- Every serious playbook should use at least 2 timeframes.
- H4 for directional bias, M15 for entry timing is the most common pairing.
- H1/M5 is an alternative for faster trading styles.

### Roles
| Timeframe | Role | What to Check |
|---|---|---|
| H4 (or Daily) | Filter | Structure direction, premium/discount zone, kernel trend, EMA position |
| M15 (or M5) | Trigger | OB/FVG zone entry, RSI extremes, pattern completion, candle signals |
| M15 | Confirmation | Second indicator agreeing with trigger on same timeframe |
| Both | Management | H4 structure for TP, M15 ATR for SL sizing |

### Phase Design Pattern

```
idle: H4 bias established (structure/trend/EMA) → wait
wait: M15 entry zone reached (OB/FVG/envelope) → entry
entry: M15 momentum confirms (RSI/MACD) → execute
in_position: H4 targets, M15 trail → idle
```

### Playbook JSON — Full Multi-TF Example

**Phase 1 — Idle (H4 directional bias):**
```json
{
  "phase": "idle",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "H4 structure bullish"},
      {"left": "ind.h4_nw_envelope.nw_bullish", "operator": "==", "right": "1", "description": "H4 kernel confirms uptrend"},
      {"left": "_price", "operator": "<", "right": "ind.h4_smc_structure.equilibrium", "description": "Price in H4 discount zone"}
    ]
  },
  "transitions": [{"target": "wait"}]
}
```

**Phase 2 — Wait (M15 entry zone):**
```json
{
  "phase": "wait",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_smc_structure.trend", "operator": "==", "right": "1", "description": "M15 structure aligns bullish with H4"},
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "1", "description": "M15 bullish OB available"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price entering M15 OB"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price within OB"}
    ]
  },
  "transitions": [{"target": "entry"}]
}
```

**Phase 3 — Entry (M15 momentum):**
```json
{
  "phase": "entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_rsi.value", "operator": "<", "right": "35", "description": "M15 RSI oversold at entry zone"},
      {"left": "ind.m15_ob_fvg.combined_partial", "operator": "==", "right": "1", "description": "M15 OB + FVG or OB + ZZ confluence"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Phase 4 — In Position (mixed TF management):**
```json
{
  "phase": "in_position",
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_smc_structure.strong_low",
    "offset": "-1.0",
    "description": "SL at H4 strong low — structural invalidation"
  },
  "take_profit": {
    "type": "indicator",
    "reference": "ind.h4_smc_structure.swing_high",
    "description": "TP at H4 swing high"
  },
  "trailing_stop": {
    "type": "indicator",
    "reference": "ind.m15_nw_envelope.lower_near",
    "description": "Trail using M15 NW lower near — tighter than H4, follows price closely"
  }
}
```

### XAUUSD Tuning
- **H4 + M15** is the optimal pairing for XAUUSD. H4 captures the daily swing structure; M15 gives 4-6 entry opportunities per day.
- **Do not use Daily + M5** — the timeframe gap is too large. Structure on Daily may not be relevant to M5 noise.
- **H1 bridge:** If H4 and M15 disagree, check H1 as a tiebreaker. If H1 aligns with H4, proceed.
- **M15 structure breaks during London open** are the highest-probability M15 signals when they align with H4 bias.

---

## 7. Combination 6: Full SMC Stack

**Indicators:** SMC_Structure + OB_FVG + NW_Envelope + ATR

### When to Use
- Maximum confluence institutional trading.
- When you want the highest win rate and are willing to accept fewer signals.
- XAUUSD primary strategy — this is the most comprehensive combination for gold.
- Experienced traders who understand all four indicators.

### Roles
| Indicator | Role | Purpose |
|---|---|---|
| SMC_Structure (H4) | Filter | Trend direction, discount/premium, invalidation levels |
| NW_Envelope (H4) | Filter + Confirmation | Trend confirmation via kernel, overextension detection |
| OB_FVG (M15) | Trigger | Precise entry at OB or FVG with confluence scoring |
| ATR (M15) | Management | Position sizing, stop loss calibration |

### Phase Design Pattern

```
idle: H4 structure bullish + H4 kernel bullish + discount zone → wait
wait: M15 OB detected + NW shows not overextended → entry
entry: OB + FVG confluence + price in OTE zone → execute
in_position: SL at strong_low, TP at swing_high, trail with NW near → idle
```

### Playbook JSON — Complete 4-Phase Example

**Phase 1 — Idle (triple filter):**
```json
{
  "phase": "idle",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "H4 market structure is bullish"},
      {"left": "ind.h4_nw_envelope.nw_bullish", "operator": "==", "right": "1", "description": "H4 kernel regression confirms uptrend"},
      {"left": "_price", "operator": "<", "right": "ind.h4_smc_structure.equilibrium", "description": "Price in discount zone — favorable for buys"},
      {"left": "_price", "operator": ">", "right": "ind.h4_nw_envelope.lower_avg", "description": "Not at extreme oversold (avoid catching knives)"}
    ]
  },
  "transitions": [{"target": "wait"}]
}
```

**Phase 2 — Wait (M15 zone with NW filter):**
```json
{
  "phase": "wait",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "1", "description": "M15 bullish order block present"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price entered OB zone"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price within OB"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "Price within H4 OTE zone (discount)"},
      {"left": "_price", "operator": "<", "right": "ind.h4_nw_envelope.upper_near", "description": "NW confirms not overbought — room to run"}
    ]
  },
  "transitions": [{"target": "entry"}]
}
```

**Phase 3 — Entry (confluence confirmation):**
```json
{
  "phase": "entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.m15_ob_fvg.combined_partial", "operator": "==", "right": "1", "description": "OB + FVG or OB + ZigZag align — multi-layer confluence"},
      {"left": "ind.m15_smc_structure.trend", "operator": "==", "right": "1", "description": "M15 structure aligns bullish with H4"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_smc_structure.ote_bottom", "description": "Price above OTE bottom (not below 78.6% fib)"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Phase 4 — In Position (comprehensive management):**
```json
{
  "phase": "in_position",
  "position_size": {
    "type": "atr_based",
    "risk_percent": 1.0,
    "atr_reference": "ind.m15_atr.value",
    "atr_multiplier": 2.5,
    "description": "Risk 1% of account, SL distance = 2.5x M15 ATR"
  },
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_smc_structure.strong_low",
    "offset": "-1.0",
    "description": "SL below H4 strong low — if this breaks, the bullish thesis is invalid"
  },
  "take_profit_levels": [
    {
      "level": 1,
      "target": "ind.h4_smc_structure.equilibrium",
      "close_percent": 33,
      "description": "TP1: Close 33% at H4 equilibrium"
    },
    {
      "level": 2,
      "target": "ind.h4_smc_structure.swing_high",
      "close_percent": 33,
      "description": "TP2: Close 33% at H4 swing high"
    },
    {
      "level": 3,
      "target": "ind.h4_nw_envelope.upper_avg",
      "close_percent": 34,
      "description": "TP3: Close remaining 34% at NW upper average — full extension"
    }
  ],
  "trailing_stop": {
    "type": "indicator",
    "reference": "ind.m15_nw_envelope.lower_near",
    "activate_after": "tp1",
    "description": "After TP1 hit, trail stop using M15 NW lower near envelope"
  },
  "exit_conditions": {
    "type": "OR",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "H4 structure flipped bearish — emergency exit all"},
      {"left": "ind.h4_nw_envelope.nw_bearish", "operator": "==", "right": "1", "description": "H4 kernel turned bearish — trend over"},
      {"left": "_price", "operator": "<", "right": "ind.h4_smc_structure.strong_low", "description": "Price broke strong low — thesis invalid"}
    ]
  }
}
```

### XAUUSD Tuning
- This is the **gold standard** (literally) for XAUUSD trading.
- H4 SMC: `swing_length: 10`, `atr_multiplier: 0.7`
- M15 OB_FVG: `ob_strength: 4`, `fvg_min_size: 0.8`
- H4 NW: `bandwidth: 8.0` (default)
- M15 ATR: `length: 14` (default), use 2.5x multiplier for SL
- Expected signal frequency: 1-3 entries per day during London/NY sessions, 0-1 during Asian.
- Win rate expectation: 55-65% with 2:1+ R:R when all confluence aligns.
- **Avoid during NFP, FOMC, CPI** — structure breaks become unreliable. Pause playbook 30 min before/after.

---

## 8. General Principles

### Choosing the Right Combination

| Market Condition | Best Combination | Why |
|---|---|---|
| Strong trend (ADX > 30) | Trend + Momentum OR Full SMC Stack | Ride the trend with pullback entries |
| Moderate trend (ADX 20-30) | Structure + Entry OR Volatility + Trend | Balanced approach, moderate signal frequency |
| Range/Chop (ADX < 20) | Mean Reversion | Fade extremes, target midline |
| High volatility event | Pause or Mean Reversion with wide SL | Structure breaks become unreliable during news |
| Multi-session trading | Multi-TF Confluence | Required for any serious around-the-clock strategy |

### Filter vs. Trigger Placement Rule

**The cardinal rule:** Higher-timeframe indicators should ALWAYS be filters (earlier phases). Lower-timeframe indicators should ALWAYS be triggers (later phases). Never use M15 as a filter for H4 triggers.

```
CORRECT:  H4 filter → M15 trigger
WRONG:    M15 filter → H4 trigger
```

### Number of Conditions Per Phase

| Phase | Recommended Rules | Rationale |
|---|---|---|
| Idle | 2-3 | Broad filter — do not over-constrain |
| Wait | 2-4 | Zone identification — specific but not too narrow |
| Entry | 2-3 | Confirmation — keep tight to avoid missing signals |
| In Position | 1-2 exit rules | Clear invalidation — do not add too many exit conditions that cause premature exits |

### Avoiding Over-Optimization

1. **Do not use more than 4 indicators total.** Each additional indicator reduces signal frequency exponentially. 3 is ideal, 4 is maximum.
2. **Do not require `combined_all` — use `combined_partial`.** Full confluence is rare; partial confluence provides enough edge.
3. **Do not optimize RSI thresholds to exact values.** Use round numbers: 30/70, 35/65, 25/75. Exact values like 32.5/67.8 are overfit.
4. **Test parameter sensitivity.** If changing a threshold by 2-3 points dramatically changes results, the parameter is fragile and should be loosened.

### XAUUSD Session-Based Strategy Selection

| Session | Time (UTC) | Recommended Combination | Notes |
|---|---|---|---|
| Asian | 00:00-06:00 | Mean Reversion | Low volatility, ranges $5-$15 |
| London Open | 07:00-09:00 | Full SMC Stack | Highest quality structure breaks |
| London | 09:00-12:00 | Structure + Entry | Continuation of London move |
| NY Open | 13:00-15:00 | Full SMC Stack OR Trend + Momentum | Second major move of the day |
| NY Afternoon | 15:00-20:00 | Multi-TF Confluence | Lower volatility, selective entries |
| Late NY | 20:00-00:00 | No trading or Mean Reversion | Low liquidity, wide spreads |
