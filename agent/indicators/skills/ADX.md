# ADX (Average Directional Index) — Playbook Skills

## Overview

The Average Directional Index (ADX) measures trend strength on a scale of 0 to 100 without
indicating trend direction. It is derived from the Directional Movement System developed by
J. Welles Wilder. The ADX line tells you how strong the trend is, while the companion +DI
(Plus Directional Indicator) and -DI (Minus Directional Indicator) lines reveal trend direction.

ADX is the premier trend filter indicator. Its primary role in playbooks is to classify the
market regime (trending vs ranging) so the playbook builder can select the appropriate strategy
type. Mean-reversion strategies should require ADX < 20-25, while trend-following strategies
should require ADX > 25.

**Indicator ID format:** `ind.<tf>_adx` (e.g., `ind.h4_adx`, `ind.h1_adx`)

**Outputs:**
| Field     | Access Expression           | Description                              |
|-----------|-----------------------------|------------------------------------------|
| adx       | `ind.h4_adx.adx`           | ADX value (0-100, trend strength)        |
| plus_di   | `ind.h4_adx.plus_di`       | +DI value (bullish directional strength) |
| minus_di  | `ind.h4_adx.minus_di`      | -DI value (bearish directional strength) |

**Previous bar access:** `prev.h4_adx.adx`, `prev.h4_adx.plus_di`, `prev.h4_adx.minus_di`

### ADX Strength Levels
| ADX Value | Trend Strength     | Market Regime    | Strategy Type          |
|-----------|--------------------|------------------|------------------------|
| 0 - 15    | Absent             | Choppy / Dead    | Avoid trading          |
| 15 - 20   | Weak               | Ranging          | Mean-reversion OK      |
| 20 - 25   | Developing         | Early trend      | Watch for confirmation |
| 25 - 40   | Strong             | Established trend| Trend-following        |
| 40 - 50   | Very strong        | Strong trend     | Aggressive trend trades|
| 50 - 75   | Extremely strong   | Powerful trend   | Stay with trend, no counter-trades |
| 75 - 100  | Rare / Exhaustion  | Climactic move   | Potential reversal zone|

---

## When to Use

### Market Conditions
- **Always as a regime filter.** ADX should be in most playbooks to prevent applying the
  wrong strategy type to the wrong market condition.
- **Trend confirmation.** Before entering a trend-following trade, confirm ADX > 25.
- **Range confirmation.** Before entering a mean-reversion trade, confirm ADX < 25.
- **Trend strength tracking.** Rising ADX = strengthening trend. Falling ADX = weakening trend.
- **DI crossovers.** +DI crossing above -DI = bullish signal. -DI crossing above +DI = bearish.

### Best Timeframes
| Timeframe | ADX Use Case                                          |
|-----------|-------------------------------------------------------|
| M15 / M30 | Intraday regime classification, DI crossover scalps   |
| H1        | Session-level trend detection                         |
| H4        | **Primary regime filter**, swing trade trend confirmation |
| D1        | Macro trend strength, position trade filter           |

### XAUUSD-Specific Considerations
- Gold frequently transitions between strong trends and ranges. ADX is essential for
  detecting these transitions.
- XAUUSD tends to have higher ADX readings than forex pairs during trending periods because
  gold trends are driven by macro fundamentals (rates, dollar, geopolitics) that persist.
- ADX > 40 on XAUUSD H4 is relatively common during macro-driven moves and can persist for
  weeks. Do not interpret ADX > 40 as "overbought" — it just means the trend is very strong.
- During Asian session, ADX often drops below 20 on H1 as gold enters a holding pattern.
  This does not mean the D1 trend has ended.

---

## Parameters Guide

| Parameter | Default | Effect of Lower             | Effect of Higher            | XAUUSD Recommendation       |
|-----------|---------|-----------------------------|-----------------------------|------------------------------|
| period    | 14      | Faster ADX response, more DI crosses, noisier | Slower, smoother, misses quick trend changes | 14 (standard) or 20 for D1 |

**Period tuning for XAUUSD:**
- **Period 14** works well for H1 and H4. It detects trend changes within 3-5 bars.
- **Period 10** can be used on M15/M30 for faster regime detection in scalping.
- **Period 20** is recommended for D1 to avoid false trend signals from daily noise.
- Avoid period < 10 as the ADX becomes too reactive to individual bars and oscillates
  between trending/ranging readings too frequently.

---

## Key Patterns & Setups

### Pattern 1: Trend Filter (ADX > 25 Gate)

**Description:** The most fundamental ADX pattern. Only allow trend-following entries when
ADX confirms a trend exists. This single filter eliminates a large percentage of losing
trades that occur in ranging markets where trend strategies fail.

**Playbook conditions (trend filter — add to trend strategies):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "25",
      "description": "ADX above 25 — market is trending (trend strategies allowed)"
    }
  ]
}
```

**Playbook conditions (range filter — add to mean-reversion strategies):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.adx",
      "operator": "<",
      "right": "25",
      "description": "ADX below 25 — market is ranging (mean-reversion allowed)"
    }
  ]
}
```

---

### Pattern 2: DI Crossover for Trend Direction

**Description:** When +DI crosses above -DI, bullish momentum is dominant. When -DI crosses
above +DI, bearish momentum is dominant. DI crossovers provide directional signals that
complement the ADX strength reading.

**Important:** DI crossovers alone generate many false signals. Always require ADX > 20-25
alongside DI crossovers for reliability.

**Playbook conditions (bullish DI crossover):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.plus_di",
      "operator": ">",
      "right": "ind.h4_adx.minus_di",
      "description": "+DI above -DI — bullish direction"
    },
    {
      "left": "prev.h4_adx.plus_di",
      "operator": "<=",
      "right": "prev.h4_adx.minus_di",
      "description": "Previous bar had -DI above +DI (crossover just happened)"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "20",
      "description": "ADX above 20 — crossover in a trending environment"
    }
  ]
}
```

**Playbook conditions (bearish DI crossover):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.minus_di",
      "operator": ">",
      "right": "ind.h4_adx.plus_di",
      "description": "-DI above +DI — bearish direction"
    },
    {
      "left": "prev.h4_adx.minus_di",
      "operator": "<=",
      "right": "prev.h4_adx.plus_di",
      "description": "Previous bar had +DI above -DI (bearish crossover just happened)"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "20",
      "description": "ADX above 20 — crossover has strength behind it"
    }
  ]
}
```

---

### Pattern 3: ADX Rising from Below 20 (Trend Initiation)

**Description:** When ADX rises from below 20 to above 20-25, a new trend is beginning.
This is one of the earliest trend detection signals. Combine with DI direction to determine
which way the trend is heading.

**Playbook conditions (new uptrend forming):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "22",
      "description": "ADX has risen above 22 — trend developing"
    },
    {
      "left": "prev.h4_adx.adx",
      "operator": "<",
      "right": "20",
      "description": "Previous ADX was below 20 — emerging from range"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "prev.h4_adx.adx",
      "description": "ADX is rising (trend strengthening)"
    },
    {
      "left": "ind.h4_adx.plus_di",
      "operator": ">",
      "right": "ind.h4_adx.minus_di",
      "description": "+DI dominant — bullish trend direction"
    }
  ]
}
```

**Notes:** This pattern catches trends early but can produce false signals during choppy
transitions. Adding a momentum indicator (RSI > 50 or MACD positive) reduces false triggers.

---

### Pattern 4: ADX Turning Point — Trend Weakening

**Description:** When ADX peaks and starts declining while still above 25, the trend is
losing momentum. This does NOT mean the trend has reversed — it means the trend is slowing.
Use this to tighten trailing stops, take partial profits, or avoid new trend entries.

**Playbook conditions (trend weakening — tighten management):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "30",
      "description": "ADX still above 30 — was in a strong trend"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": "<",
      "right": "prev.h4_adx.adx",
      "description": "ADX declining — trend momentum fading"
    }
  ]
}
```

**Action on trend weakening:**
- Move trailing stop tighter (from 2x ATR to 1.5x ATR).
- Take partial profits (close 30-50% of position).
- Do not enter new trend trades until ADX starts rising again or a new DI crossover occurs.

---

### Pattern 5: DI Spread as Trend Confidence

**Description:** The spread between +DI and -DI indicates how dominant one direction is.
A large spread (e.g., +DI at 35, -DI at 12, spread = 23) indicates strong directional
conviction. A narrow spread (e.g., +DI at 22, -DI at 19, spread = 3) indicates weak or
uncertain direction even if ADX is above 25.

**Playbook conditions (strong bullish conviction):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "25",
      "description": "Market is trending"
    },
    {
      "left": "ind.h4_adx.plus_di",
      "operator": ">",
      "right": "ind.h4_adx.minus_di",
      "description": "Bullish direction"
    },
    {
      "left": "ind.h4_adx.plus_di - ind.h4_adx.minus_di",
      "operator": ">",
      "right": "10",
      "description": "DI spread > 10 — strong directional conviction"
    }
  ]
}
```

**DI spread interpretation for XAUUSD:**
| DI Spread   | Interpretation                              | Action              |
|-------------|---------------------------------------------|---------------------|
| < 5         | No clear direction — avoid                  | Skip trade          |
| 5 - 10      | Mild directional bias                       | Small position only  |
| 10 - 20     | Clear directional momentum                  | Standard position    |
| > 20        | Strong directional dominance                | Full position, trend follow |

---

## Combinations

| Combo Indicator     | Purpose                           | Confluence Type      | Example                                      |
|---------------------|-----------------------------------|----------------------|----------------------------------------------|
| + ATR               | Trend strength + volatility       | Regime + sizing      | ADX > 25 + ATR rising = strong trending move |
| + EMA (50/200)      | Trend strength + direction        | Dual trend confirm   | ADX > 25 + price above EMA 50 = confirmed uptrend |
| + Bollinger Bands   | Regime-dependent band strategy    | Strategy selector    | ADX < 25 = mean revert at bands; ADX > 25 = trade band walks |
| + RSI               | Trend + overbought/oversold      | Entry timing         | ADX > 25 + RSI pullback to 40-50 = trend continuation entry |
| + MACD              | Trend strength + momentum        | Dual confirmation    | ADX > 25 + MACD positive = strong bullish trend |
| + Stochastic        | Range confirmation + timing      | Entry timing         | ADX < 20 + Stochastic at 20 = mean-reversion long |
| + CCI               | Trend + momentum extremes        | Entry confirmation   | ADX > 30 + CCI > 100 = strong trend with momentum |
| + SMC_Structure     | Institutional trend + ADX strength| Structural filter    | SMC bullish trend + ADX > 25 = high-confidence long |

**Best combination for XAUUSD:** ADX + EMA(50) + ATR. ADX confirms trend existence, EMA
provides direction, ATR sizes the trade. This trio forms the backbone of robust trend systems.

---

## Position Management

### ADX-Based Position Sizing

Scale position size with ADX trend strength:

| ADX Range | Position Size  | Rationale                                |
|-----------|----------------|------------------------------------------|
| < 20      | 0% (no trade)  | No trend, don't enter trend trades       |
| 20 - 30   | 50% of max     | Developing trend, moderate conviction    |
| 30 - 40   | 75% of max     | Strong trend, good conviction            |
| 40 - 50   | 100% of max    | Very strong trend, maximum conviction    |
| > 50      | 75% of max     | Very strong but potentially extended     |

### Trailing Stop Adjustment by ADX

Adjust trailing stop tightness based on ADX:

```json
{
  "trailing_stop": {
    "type": "conditional",
    "rules": [
      {
        "condition": "ind.h4_adx.adx > 40",
        "long_trail_expr": "_price - ind.h4_atr.value * 2.5",
        "description": "Wide trail for very strong trends (ADX > 40)"
      },
      {
        "condition": "ind.h4_adx.adx > 25",
        "long_trail_expr": "_price - ind.h4_atr.value * 2.0",
        "description": "Standard trail for strong trends (ADX 25-40)"
      },
      {
        "condition": "ind.h4_adx.adx < 25",
        "long_trail_expr": "_price - ind.h4_atr.value * 1.0",
        "description": "Tight trail when trend weakens (ADX < 25)"
      }
    ]
  }
}
```

### Exit on ADX Collapse

When ADX drops below 20 after being above 30, the trend has likely ended. This is a signal
to close remaining positions:

```json
{
  "exit_condition": {
    "type": "AND",
    "rules": [
      {
        "left": "ind.h4_adx.adx",
        "operator": "<",
        "right": "20",
        "description": "ADX collapsed below 20 — trend is over"
      },
      {
        "left": "prev.h4_adx.adx",
        "operator": ">",
        "right": "25",
        "description": "Was recently in a trend — this is a trend termination"
      }
    ]
  }
}
```

---

## Pitfalls

1. **Using ADX for direction.** ADX only measures strength, NOT direction. An ADX of 40
   could be a strong uptrend or a strong downtrend. Always check +DI vs -DI for direction.
   This is the single most common ADX mistake.

2. **Treating ADX < 20 as "no trade possible."** Low ADX means no trend — but mean-reversion
   strategies thrive in low-ADX environments. ADX < 20 is a signal to switch strategy type,
   not to stop trading entirely.

3. **Expecting ADX to reach high levels on lower timeframes.** On M5/M15, ADX rarely exceeds
   40 because intrabar noise dilutes directional readings. Adjust your thresholds lower for
   shorter timeframes. Use ADX > 20 (not 25) on M15.

4. **Ignoring the difference between rising and falling ADX.** ADX at 30 and rising is very
   different from ADX at 30 and falling. Rising ADX = trend strengthening, ideal for new
   entries. Falling ADX = trend weakening, take profits or tighten stops.

5. **Using DI crossovers without ADX confirmation.** DI crossovers in a ranging market
   (ADX < 20) are meaningless noise. They whipsaw back and forth constantly. Only trade DI
   crossovers when ADX > 20.

6. **Not accounting for ADX lag.** ADX is derived from a smoothed average and lags price by
   several bars. By the time ADX rises above 25, the trend may be 5-8 bars old. Accept
   this lag — trying to front-run ADX with lower periods just creates noise.

7. **Confusing ADX with RSI.** Unlike RSI, ADX has no "overbought" level. ADX at 60 does
   not mean the market is overbought. It means the trend is extremely strong. The only
   cautionary ADX level is > 75, which is rare and may indicate a climactic exhaustion move.

---

## XAUUSD-Specific Notes

### Gold ADX Behavioral Patterns

Gold's ADX behavior differs from forex pairs in several important ways:

- **Higher sustained ADX readings.** XAUUSD can maintain ADX > 40 for weeks during macro
  trends (e.g., rate cut cycles, geopolitical risk). Forex pairs rarely sustain ADX > 40
  for more than a few days.
- **Sharper ADX transitions.** Gold tends to transition abruptly between trending and
  ranging rather than gradually. ADX can jump from 15 to 30 in 3-4 H4 bars when a catalyst
  hits (unexpected Fed commentary, geopolitical event).
- **Asian session ADX drain.** On H1, ADX regularly drops below 15 during the Asian session
  even when a strong D1 trend exists. Do not use H1 ADX during Asian hours as a regime
  filter — use H4 or D1 ADX instead.

### XAUUSD ADX Thresholds (adjusted for gold)

| Timeframe | No Trend | Developing | Strong Trend | Very Strong |
|-----------|----------|------------|--------------|-------------|
| M15       | < 18     | 18 - 22    | 22 - 35      | > 35        |
| H1        | < 20     | 20 - 25    | 25 - 40      | > 40        |
| H4        | < 20     | 20 - 25    | 25 - 45      | > 45        |
| D1        | < 20     | 20 - 28    | 28 - 50      | > 50        |

### Combining ADX with Gold Sessions

| Session         | Typical ADX (H1)   | DI Behavior                      | Strategy Note                   |
|-----------------|---------------------|----------------------------------|---------------------------------|
| Asian           | 10 - 18             | +DI and -DI close together       | Avoid trend trades, scalp range |
| London Open     | 18 - 30 (rising)    | DI separation begins             | Watch for trend initiation      |
| NY Open         | 25 - 40             | Clear DI separation              | Prime trend trading window      |
| London/NY Overlap| 30 - 50+           | Maximum DI separation            | Strongest trends, full size     |
| Post-NY         | Declining from peak  | DI converging                    | Tighten stops, no new entries   |

### Universal ADX Regime Filter for XAUUSD Playbooks

Include this in trend-following playbooks:
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "25",
      "description": "H4 ADX confirms trending market"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "prev.h4_adx.adx",
      "description": "ADX is rising — trend is strengthening"
    }
  ]
}
```

Include this in mean-reversion playbooks:
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_adx.adx",
      "operator": "<",
      "right": "22",
      "description": "H4 ADX below 22 — ranging market, mean-reversion appropriate"
    }
  ]
}
```
