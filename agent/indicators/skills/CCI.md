# CCI (Commodity Channel Index) — Playbook Skills

## Overview

The Commodity Channel Index (CCI) measures the deviation of price from its statistical mean.
It is calculated as: `CCI = (Typical Price - SMA of Typical Price) / (0.015 * Mean Deviation)`.
The 0.015 constant ensures that roughly 70-80% of CCI values fall between -100 and +100.

CCI is an unbounded oscillator — unlike RSI (0-100), CCI can reach -300, +400, or beyond.
This makes it particularly useful for detecting extreme momentum conditions and for
identifying when price has moved far beyond its typical range.

**Indicator ID format:** `ind.<tf>_cci` (e.g., `ind.h4_cci`, `ind.h1_cci`)

**Outputs:**
| Field | Access Expression       | Description                              |
|-------|-------------------------|------------------------------------------|
| value | `ind.h4_cci.value`      | CCI value (unbounded, typically -200 to +200) |

**Previous bar access:** `prev.h4_cci.value`

### CCI Level Reference
| CCI Value  | Interpretation           | Market State                    |
|------------|--------------------------|---------------------------------|
| > +200     | Extreme overbought       | Potential exhaustion / reversal  |
| +100 to +200 | Overbought            | Bullish momentum, watch for fade|
| 0 to +100  | Mildly bullish           | Bullish bias, normal range      |
| -100 to 0  | Mildly bearish           | Bearish bias, normal range      |
| -100 to -200| Oversold               | Bearish momentum, watch for bounce|
| < -200     | Extreme oversold         | Potential exhaustion / reversal  |

---

## When to Use

### Market Conditions
- **Trend identification:** CCI crossing above zero = bullish bias, below zero = bearish bias.
- **Overbought/oversold detection:** CCI at +100/-100 marks traditional overbought/oversold.
  Extreme levels (+200/-200) mark potential reversal zones.
- **Momentum measurement:** CCI measures how far price has deviated from its mean, making it
  a direct momentum gauge. Rising CCI = accelerating momentum.
- **Divergence detection:** When price makes new highs but CCI makes lower highs (bearish
  divergence) or price makes new lows but CCI makes higher lows (bullish divergence).

### Best Timeframes
| Timeframe | CCI Use Case                                          |
|-----------|-------------------------------------------------------|
| M5 / M15  | Scalping overbought/oversold extremes                 |
| M30 / H1  | Intraday momentum detection, divergence               |
| H4        | **Primary swing momentum**, zero-line trend filter    |
| D1        | Macro momentum direction, extreme reversal detection  |

### XAUUSD-Specific Considerations
- Gold's tendency for strong momentum means CCI frequently reaches extreme levels (+200/-200
  and beyond) during macro-driven moves.
- CCI at +/-100 is less reliable on XAUUSD than on calmer instruments because gold's
  volatility pushes CCI to those levels routinely. Use +/-150 or +/-200 for XAUUSD as
  "meaningful" overbought/oversold.
- Multi-timeframe CCI works exceptionally well on gold: use D1 CCI for direction and H4
  CCI for entry timing.
- CCI period 20 is recommended for XAUUSD (vs default 14) because it smooths out gold's
  intrabar noise while still being responsive to genuine momentum shifts.

---

## Parameters Guide

| Parameter | Default | Effect of Lower              | Effect of Higher              | XAUUSD Recommendation       |
|-----------|---------|------------------------------|-------------------------------|-----------------------------|
| period    | 14      | More sensitive, reaches extremes faster, more noise | Smoother, slower to reach extremes, fewer signals | **20** for XAUUSD          |

**Why period 20 for XAUUSD:**
- CCI with period 14 on gold generates too many false overbought/oversold signals because
  gold's high volatility pushes short-period CCI to extremes constantly.
- Period 20 provides a better balance: it still reaches +/-200 during genuine momentum
  moves but filters out noise during normal oscillations.
- On M15 for scalping, period 14 can be used as the intent is to capture fast moves.
- On D1, period 20-25 works well for macro momentum assessment.

**Alternative periods:**
| Period | Best For                            | XAUUSD Notes                     |
|--------|-------------------------------------|----------------------------------|
| 10     | Fast scalping (M5/M15)              | Very noisy, many false extremes  |
| 14     | Standard (forex)                    | Too sensitive for gold's volatility|
| 20     | **Recommended for XAUUSD (all TFs)**| Good balance of signal quality   |
| 30     | Long-term macro direction           | Slow, use only on D1/W1         |

---

## Key Patterns & Setups

### Pattern 1: CCI Overbought/Oversold Reversal

**Description:** When CCI reaches extreme levels (+200/-200), it indicates price has moved
far from its mean. This often (not always) precedes a pullback or reversal. The deeper into
extreme territory CCI goes, the stronger the expected reversion.

**Critical distinction:** CCI overbought/oversold works for mean-reversion in ranging
markets. In strong trends, CCI can stay overbought/oversold for extended periods (similar to
RSI). Always check ADX to determine market regime.

**Playbook conditions (long — oversold reversal in range):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_cci.value",
      "operator": "<",
      "right": "-150",
      "description": "CCI deeply oversold (below -150 for XAUUSD)"
    },
    {
      "left": "ind.h4_cci.value",
      "operator": ">",
      "right": "prev.h4_cci.value",
      "description": "CCI turning up from oversold (momentum shift)"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": "<",
      "right": "25",
      "description": "ADX confirms ranging market — reversal is valid"
    }
  ]
}
```

**Playbook conditions (short — overbought reversal in range):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_cci.value",
      "operator": ">",
      "right": "150",
      "description": "CCI overbought (above +150 for XAUUSD)"
    },
    {
      "left": "ind.h4_cci.value",
      "operator": "<",
      "right": "prev.h4_cci.value",
      "description": "CCI turning down from overbought"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": "<",
      "right": "25",
      "description": "Ranging market — overbought fade is appropriate"
    }
  ]
}
```

---

### Pattern 2: Zero-Line Crossover (Trend Direction)

**Description:** CCI crossing above zero indicates price is above its average — bullish bias.
CCI crossing below zero indicates price is below its average — bearish bias. This is the
simplest CCI trend signal and works well as a directional filter.

**Playbook conditions (bullish zero-line crossover):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_cci.value",
      "operator": ">",
      "right": "0",
      "description": "CCI above zero — bullish bias"
    },
    {
      "left": "prev.h4_cci.value",
      "operator": "<=",
      "right": "0",
      "description": "Previous CCI was at or below zero (fresh crossover)"
    }
  ]
}
```

**Playbook conditions (bearish zero-line crossover):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_cci.value",
      "operator": "<",
      "right": "0",
      "description": "CCI below zero — bearish bias"
    },
    {
      "left": "prev.h4_cci.value",
      "operator": ">=",
      "right": "0",
      "description": "Previous CCI was at or above zero (fresh crossover)"
    }
  ]
}
```

**Enhancement:** Require ADX > 20 alongside the zero-line crossover to confirm the
crossover is happening in a market with some directional movement, not just noise.

---

### Pattern 3: CCI Trend Following (+100/-100 Breakout)

**Description:** In trending markets, CCI breaking above +100 signals strong bullish
momentum, and breaking below -100 signals strong bearish momentum. Unlike the reversal
strategy, this pattern treats +100/-100 as momentum breakout levels.

**Key requirement:** ADX > 25 confirms trend. CCI in a trend acts as a momentum accelerator,
not a reversal signal.

**Playbook conditions (bullish momentum breakout):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_cci.value",
      "operator": ">",
      "right": "100",
      "description": "CCI breaks above +100 — strong bullish momentum"
    },
    {
      "left": "prev.h4_cci.value",
      "operator": "<=",
      "right": "100",
      "description": "Fresh breakout above +100"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "25",
      "description": "ADX confirms trending market — momentum is real"
    },
    {
      "left": "ind.h4_adx.plus_di",
      "operator": ">",
      "right": "ind.h4_adx.minus_di",
      "description": "+DI dominant — bullish trend direction confirmed"
    }
  ]
}
```

**Notes:** When CCI breaks +100 in a confirmed trend, the move often extends to +150 or
+200 before a meaningful pullback. Do not immediately look for reversals at +100 in trends.

---

### Pattern 4: CCI Divergence (Hidden and Regular)

**Description:** Divergence between price and CCI provides early warning of trend weakening
or continuation.

- **Regular bearish divergence:** Price makes higher high, CCI makes lower high. Warns of
  potential reversal from uptrend.
- **Regular bullish divergence:** Price makes lower low, CCI makes higher low. Warns of
  potential reversal from downtrend.
- **Hidden bullish divergence:** Price makes higher low, CCI makes lower low. Trend
  continuation signal (buy the dip).
- **Hidden bearish divergence:** Price makes lower high, CCI makes higher high. Trend
  continuation signal (sell the rally).

**Playbook conditions (bullish divergence approximation):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_cci.value",
      "operator": "<",
      "right": "-100",
      "description": "CCI in oversold territory"
    },
    {
      "left": "ind.h4_cci.value",
      "operator": ">",
      "right": "prev.h4_cci.value",
      "description": "CCI making higher low (turning up)"
    },
    {
      "left": "ind.h4_rsi.value",
      "operator": "<",
      "right": "40",
      "description": "RSI confirms weak price (supporting divergence read)"
    }
  ]
}
```

**Note:** True divergence detection requires comparing swing highs/lows across multiple
bars, which is difficult in single-bar condition rules. The approximation above captures
the essence: CCI turning up from deep oversold while price is still weak. For higher
accuracy, combine with SMC_Structure swing detection.

---

### Pattern 5: Multi-Timeframe CCI (Direction + Entry)

**Description:** Use higher-timeframe CCI for direction bias and lower-timeframe CCI for
entry timing. This is one of the most powerful CCI applications.

- **D1 CCI > 0:** Bullish daily bias. Only take long entries on H4.
- **D1 CCI < 0:** Bearish daily bias. Only take short entries on H4.
- **H4 CCI pullback to -100 in bullish D1:** Buy the dip — CCI oversold on entry TF while
  higher TF is bullish.

**Playbook conditions (multi-TF bullish — D1 direction, H4 entry):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.d1_cci.value",
      "operator": ">",
      "right": "0",
      "description": "D1 CCI above zero — bullish daily bias"
    },
    {
      "left": "ind.h4_cci.value",
      "operator": "<",
      "right": "-100",
      "description": "H4 CCI oversold — pullback within the bullish daily trend"
    },
    {
      "left": "ind.h4_cci.value",
      "operator": ">",
      "right": "prev.h4_cci.value",
      "description": "H4 CCI turning up — pullback reversal beginning"
    }
  ]
}
```

**Playbook conditions (multi-TF bearish — D1 direction, H4 entry):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.d1_cci.value",
      "operator": "<",
      "right": "0",
      "description": "D1 CCI below zero — bearish daily bias"
    },
    {
      "left": "ind.h4_cci.value",
      "operator": ">",
      "right": "100",
      "description": "H4 CCI overbought — rally within bearish daily trend"
    },
    {
      "left": "ind.h4_cci.value",
      "operator": "<",
      "right": "prev.h4_cci.value",
      "description": "H4 CCI turning down — rally failing"
    }
  ]
}
```

---

## Combinations

| Combo Indicator     | Purpose                           | Confluence Type      | Example                                      |
|---------------------|-----------------------------------|----------------------|----------------------------------------------|
| + ADX               | Regime classification             | Strategy selector    | ADX < 25 → CCI reversal; ADX > 25 → CCI trend follow |
| + ATR               | Volatility-adjusted SL/TP        | Sizing               | CCI signal + ATR-based stops                 |
| + RSI               | Dual momentum confirmation       | Entry confirmation   | CCI < -150 + RSI < 30 = strong oversold     |
| + Bollinger Bands   | Price extremes + momentum        | Dual confirmation    | At lower band + CCI < -100 = high-prob reversal|
| + EMA (50)          | Trend direction + CCI timing     | Direction + entry    | Above EMA50 + CCI pullback to 0 = buy dip   |
| + MACD              | Momentum crossover confirmation  | Dual momentum        | CCI zero cross + MACD crossover = strong signal|
| + Stochastic        | Dual oscillator at extremes      | Entry confirmation   | CCI < -150 + Stoch < 20 = maximum oversold  |
| + SMC_Structure     | Structural + momentum            | Zone + momentum      | CCI oversold at bullish OB = institutional entry|
| + WilliamsR         | Triple oscillator confluence     | Entry timing         | CCI < -100 + WR < -80 = deep oversold       |

**Best combination for XAUUSD:** CCI + ADX + ATR. ADX selects strategy type, CCI provides
momentum-based entry signals, ATR sizes the trade. For entries, CCI + RSI dual confirmation
at extremes filters out many false signals.

---

## Position Management

### Dynamic Stop Loss — CCI Zero-Line

For trend trades entered on CCI momentum breakout (> +100), use CCI returning to zero as
the stop signal:

```json
{
  "exit_condition": {
    "type": "AND",
    "rules": [
      {
        "left": "ind.h4_cci.value",
        "operator": "<",
        "right": "0",
        "description": "CCI crossed below zero — momentum has fully reversed, exit long"
      }
    ]
  }
}
```

### CCI-Based Trailing

Trail based on CCI turning points. In a long trade, when CCI starts declining from a peak
above +100, tighten the trailing stop:

```json
{
  "trailing_stop": {
    "type": "conditional",
    "rules": [
      {
        "condition": "ind.h4_cci.value > 100",
        "long_trail_expr": "_price - ind.h4_atr.value * 2.5",
        "description": "Wide trail while CCI shows strong momentum"
      },
      {
        "condition": "ind.h4_cci.value > 0",
        "long_trail_expr": "_price - ind.h4_atr.value * 1.5",
        "description": "Standard trail — CCI positive but not extreme"
      },
      {
        "condition": "ind.h4_cci.value < 0",
        "long_trail_expr": "_price - ind.h4_atr.value * 0.5",
        "description": "Very tight trail — CCI has gone negative, exit imminent"
      }
    ]
  }
}
```

### Take Profit at CCI Extremes

For mean-reversion trades entered at CCI extremes, target the zero line or the opposite
extreme for partial profits:

```json
{
  "take_profit": {
    "tp1_condition": "ind.h4_cci.value > 0",
    "tp1_portion": 0.5,
    "tp1_description": "Close 50% when CCI reaches zero (mean reversion complete)",
    "tp2_condition": "ind.h4_cci.value > 100",
    "tp2_portion": 0.5,
    "tp2_description": "Close remaining 50% when CCI reaches +100 (full extension)"
  }
}
```

---

## Pitfalls

1. **Treating CCI +100/-100 as automatic reversal signals.** In trending markets, CCI can
   stay above +100 for many bars. Fading +100 in an uptrend is a losing strategy. Always
   check ADX before deciding whether CCI at extremes is a reversal or continuation signal.

2. **Using default period 14 on XAUUSD.** Gold's volatility makes CCI(14) too noisy. Switch
   to CCI(20) for XAUUSD across all timeframes. This single change dramatically improves
   signal quality.

3. **Ignoring the zero line.** Many traders focus exclusively on the +100/-100 levels and
   miss the zero line. The zero-line crossover is CCI's most reliable trend signal. Price
   above its mean (CCI > 0) vs below (CCI < 0) is a powerful directional filter.

4. **Using CCI alone for entries.** CCI measures momentum but not trend strength or
   volatility. A CCI at -200 means price is far below average, but it does not tell you
   whether the move will continue (trend) or reverse (range). Always pair with ADX and ATR.

5. **Overcomplicating CCI with multiple levels.** Some systems use +50, +100, +150, +200,
   -50, -100, -150, -200 as distinct levels. This creates decision paralysis. Stick to three
   levels: 0 (trend direction), +/-100 (overbought/oversold), +/-200 (extreme). Simplicity
   wins in live trading.

6. **Not accounting for CCI's unbounded nature.** Unlike RSI which caps at 0 and 100, CCI
   can go to -500 or +500 in extreme moves. Do not assume CCI at -200 "cannot go lower."
   In a gold crash, CCI can reach -300 or beyond.

7. **Trading CCI divergence on short timeframes.** CCI divergence on M5/M15 is unreliable
   due to noise. Divergence works best on H4 and D1 where price swings are cleaner and
   more meaningful.

---

## XAUUSD-Specific Notes

### Gold CCI Behavioral Patterns

- **CCI(20) extremes are more meaningful on gold than CCI(14).** With period 20, CCI
  reaching +/-200 on XAUUSD H4 genuinely indicates extreme momentum, not routine oscillation.
- **Gold CCI tends to cluster near zero during Asian session** and then break sharply
  during London/NY. Use zero-line position at London open as a session bias indicator.
- **During gold macro trends, CCI can remain above +100 on D1 for 10-20+ bars.** Do not
  fight this. Use D1 CCI > +100 as a "strong trend" indicator and only look for pullback
  entries on lower timeframes.

### XAUUSD CCI Thresholds (adjusted for gold with period 20)

| Level     | Meaning for XAUUSD                       | Action                          |
|-----------|-------------------------------------------|---------------------------------|
| > +200    | Extreme bullish momentum (rare, powerful) | Close shorts, consider reversal only with ADX < 25 |
| +100 to +200 | Strong bullish momentum              | Trend follow or hold longs      |
| +50 to +100 | Moderate bullish bias                  | Normal long territory           |
| -50 to +50 | Neutral / consolidation                 | Wait for direction              |
| -50 to -100 | Moderate bearish bias                  | Normal short territory          |
| -100 to -200 | Strong bearish momentum              | Trend follow or hold shorts     |
| < -200    | Extreme bearish momentum                  | Close longs, consider reversal only with ADX < 25 |

### Multi-Timeframe CCI Template for XAUUSD

This is the recommended CCI setup for XAUUSD playbooks:
- **D1 CCI(20):** Macro direction filter. Only trade in the direction of D1 CCI.
- **H4 CCI(20):** Primary entry/exit signal. Use +100/-100 for entries, zero for exits.
- **H1 CCI(20):** Fine-tuning entries and exits within H4 signals.

```json
{
  "indicators": [
    {"id": "d1_cci", "name": "CCI", "timeframe": "D1", "params": {"period": 20}},
    {"id": "h4_cci", "name": "CCI", "timeframe": "H4", "params": {"period": 20}},
    {"id": "h1_cci", "name": "CCI", "timeframe": "H1", "params": {"period": 20}}
  ]
}
```

### Session-Based CCI Behavior (XAUUSD H1, period 20)

| Session              | Typical CCI Range     | Notes                             |
|----------------------|-----------------------|-----------------------------------|
| Asian (00:00-07:00)  | -50 to +50            | Near zero, low momentum           |
| London (07:00-12:00) | -100 to +100          | CCI begins moving directionally   |
| NY (12:00-17:00)     | -200 to +200          | Full range, strong momentum moves |
| London Close         | Declining from extremes| Momentum fading, avoid new entries|

### CCI as a Gold Volatility Proxy

CCI's absolute value (ignoring sign) can serve as a rough volatility proxy:
- `|CCI| < 50` → Low momentum, possibly quiet market
- `|CCI| 50-100` → Normal momentum
- `|CCI| 100-200` → High momentum, active market
- `|CCI| > 200` → Extreme momentum, news-driven or macro event

This is simpler than ATR for quick momentum checks in playbook conditions.
