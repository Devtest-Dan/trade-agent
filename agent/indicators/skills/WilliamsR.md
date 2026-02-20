# Williams %R — Playbook Skills

## Overview

Williams %R (Williams Percent Range) is a momentum oscillator that measures the level of
the close relative to the high-low range over a lookback period. It ranges from -100 to 0,
where -100 represents the lowest low and 0 represents the highest high of the period.

**Formula:** `%R = (Highest High - Close) / (Highest High - Lowest Low) * -100`

Williams %R is the inverse of the Fast Stochastic Oscillator (%K). Where Stochastic measures
the close relative to the low of the range, Williams %R measures the close relative to the
high of the range. This gives it inverted overbought/oversold zones: readings near 0 are
overbought and readings near -100 are oversold.

Williams %R is particularly effective for timing entries in trending markets. Its fast
response to price changes makes it ideal for catching pullback entries within established
trends.

**Indicator ID format:** `ind.<tf>_williamsr` (e.g., `ind.h4_williamsr`, `ind.h1_williamsr`)

**Outputs:**
| Field | Access Expression           | Description                              |
|-------|-----------------------------|------------------------------------------|
| value | `ind.h4_williamsr.value`    | Williams %R value (-100 to 0)            |

**Previous bar access:** `prev.h4_williamsr.value`

### Williams %R Level Reference
| %R Value      | Zone          | Interpretation                            |
|---------------|---------------|-------------------------------------------|
| -20 to 0      | Overbought    | Close is near the high of the range       |
| -50           | Midpoint      | Close is at the center of the range       |
| -80 to -100   | Oversold      | Close is near the low of the range        |

**Important sign convention:** Williams %R is always negative (or zero). This differs from
most oscillators. Do not confuse -80 with 80. In playbook conditions:
- Oversold check: `ind.h4_williamsr.value < -80` (more negative = more oversold)
- Overbought check: `ind.h4_williamsr.value > -20` (less negative = more overbought)

---

## When to Use

### Market Conditions
- **Trend pullback entries:** Williams %R excels at identifying pullbacks within trends.
  In an uptrend, buy when %R dips to oversold (-80). In a downtrend, sell when %R rallies
  to overbought (-20).
- **Momentum confirmation:** Williams %R staying in overbought zone confirms bullish
  momentum. Staying in oversold confirms bearish momentum.
- **Range-bound mean reversion:** In ranging markets, trade bounces at -80 and -20.
- **Failure swings:** When %R reaches an extreme, pulls back, then fails to return to
  the extreme on the next attempt — signals momentum exhaustion.

### Best Timeframes
| Timeframe | Williams %R Use Case                                  |
|-----------|-------------------------------------------------------|
| M5        | Scalping with period 10 — fast overbought/oversold    |
| M15 / M30 | Intraday pullback entries, session momentum            |
| H1        | Session-level momentum tracking                        |
| H4        | **Primary swing pullback timing**, trend entry         |
| D1        | Macro momentum assessment, position trade entries      |

### XAUUSD-Specific Considerations
- Williams %R's fast response is both a strength and weakness on XAUUSD. Gold's volatility
  causes rapid %R oscillations that can trigger premature signals.
- **Period 14 is standard for swing trades.** Period 10 is recommended for XAUUSD scalping
  as it captures gold's fast intraday moves.
- During strong gold trends (ADX > 30), Williams %R can stay in the overbought/oversold
  zone for many bars. Do not fade these readings — they are trend confirmation signals.
- Gold's session-dependent behavior means %R zones shift. During Asian session, %R oscillates
  near -50 (neutral). London/NY sessions push %R to extremes.

---

## Parameters Guide

| Parameter | Default | Effect of Lower                | Effect of Higher               | XAUUSD Recommendation        |
|-----------|---------|--------------------------------|--------------------------------|-------------------------------|
| period    | 14      | Faster, more signals, more noise, reaches extremes quicker | Smoother, fewer signals, stronger signals when they occur | 14 (swing), **10 (scalping)** |

**Period selection guide for XAUUSD:**

| Period | Best Timeframe   | Characteristics                          | Use Case                |
|--------|------------------|------------------------------------------|-------------------------|
| 7      | M5 only          | Very fast, extremely noisy               | Ultra-fast scalping only|
| 10     | M5 / M15 / M30   | Fast, captures quick gold moves          | **Scalping (recommended)**|
| 14     | H1 / H4 / D1     | Standard, balanced speed and reliability | **Swing trading (standard)**|
| 21     | H4 / D1          | Slow, high-quality but lagging           | Position trades, filters|

**Notes on period 10 for XAUUSD scalping:**
- Gold's intraday volatility means that a 14-period %R on M5/M15 lags behind fast moves.
  Period 10 detects overbought/oversold 2-3 bars earlier, which matters for scalping.
- The trade-off is more noise, but when combined with an ATR filter and trend direction
  from a higher timeframe, period 10 performs well on XAUUSD.

---

## Key Patterns & Setups

### Pattern 1: Oversold/Overbought Reversal (Range Trading)

**Description:** In ranging markets, Williams %R bouncing from oversold (-80 to -100) or
overbought (-20 to 0) provides mean-reversion entry signals. Wait for %R to leave the
extreme zone (cross back above -80 or below -20) for confirmation.

**Playbook conditions (long — oversold reversal):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_williamsr.value",
      "operator": ">",
      "right": "-80",
      "description": "Williams %R crossed back above -80 (leaving oversold)"
    },
    {
      "left": "prev.h4_williamsr.value",
      "operator": "<=",
      "right": "-80",
      "description": "Previous bar was in oversold zone (fresh exit from oversold)"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": "<",
      "right": "25",
      "description": "ADX < 25 — ranging market, mean-reversion valid"
    }
  ]
}
```

**Playbook conditions (short — overbought reversal):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_williamsr.value",
      "operator": "<",
      "right": "-20",
      "description": "Williams %R crossed below -20 (leaving overbought)"
    },
    {
      "left": "prev.h4_williamsr.value",
      "operator": ">=",
      "right": "-20",
      "description": "Previous bar was in overbought zone (fresh exit from overbought)"
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

### Pattern 2: Trend Pullback Entry (Williams %R + Trend Filter)

**Description:** In a confirmed trend, use Williams %R to time pullback entries. In an
uptrend, %R dipping to oversold (-80) represents a buying opportunity as the pullback is
exhausting. This is Williams %R's strongest pattern — catching trend pullbacks.

**Playbook conditions (bullish pullback entry):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_williamsr.value",
      "operator": "<",
      "right": "-80",
      "description": "Williams %R oversold — pullback in progress"
    },
    {
      "left": "ind.h4_williamsr.value",
      "operator": ">",
      "right": "prev.h4_williamsr.value",
      "description": "Williams %R turning up — pullback exhausting"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "25",
      "description": "ADX confirms trending market"
    },
    {
      "left": "ind.h4_adx.plus_di",
      "operator": ">",
      "right": "ind.h4_adx.minus_di",
      "description": "+DI > -DI confirms bullish direction"
    },
    {
      "left": "_price",
      "operator": ">",
      "right": "ind.h4_ema50.value",
      "description": "Price above EMA 50 — structural uptrend"
    }
  ]
}
```

**Playbook conditions (bearish pullback entry):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_williamsr.value",
      "operator": ">",
      "right": "-20",
      "description": "Williams %R overbought — rally within downtrend"
    },
    {
      "left": "ind.h4_williamsr.value",
      "operator": "<",
      "right": "prev.h4_williamsr.value",
      "description": "Williams %R turning down — rally exhausting"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "25",
      "description": "Trending market"
    },
    {
      "left": "ind.h4_adx.minus_di",
      "operator": ">",
      "right": "ind.h4_adx.plus_di",
      "description": "-DI > +DI — bearish direction"
    },
    {
      "left": "_price",
      "operator": "<",
      "right": "ind.h4_ema50.value",
      "description": "Price below EMA 50 — structural downtrend"
    }
  ]
}
```

---

### Pattern 3: Failure Swing (Momentum Exhaustion)

**Description:** A failure swing occurs when Williams %R reaches an extreme zone, exits it,
then attempts to re-enter but fails — making a higher low in oversold or a lower high in
overbought. This indicates momentum exhaustion and often precedes a reversal.

**Bullish failure swing sequence:**
1. %R drops below -80 (oversold)
2. %R bounces above -80
3. %R dips again but stays above its prior low and above -80
4. %R rises — this is the buy signal

**Playbook conditions (bullish failure swing approximation):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_williamsr.value",
      "operator": ">",
      "right": "-70",
      "description": "Williams %R well above oversold — has bounced"
    },
    {
      "left": "prev.h4_williamsr.value",
      "operator": "<",
      "right": "-70",
      "description": "Previous bar was lower — %R just turned up"
    },
    {
      "left": "prev.h4_williamsr.value",
      "operator": ">",
      "right": "-80",
      "description": "Previous dip stayed above -80 (failed to reach oversold = failure swing)"
    },
    {
      "left": "ind.h4_rsi.value",
      "operator": ">",
      "right": "40",
      "description": "RSI confirms momentum is not deeply bearish"
    }
  ]
}
```

**Notes:** True failure swing detection requires tracking 4-6 bars of %R behavior. The
approximation above captures the key signature: %R bouncing upward from above -80 after
a prior visit to oversold territory. Combine with RSI or CCI for confirmation.

---

### Pattern 4: Williams %R Zone Persistence (Trend Strength)

**Description:** In strong trends, Williams %R stays in one zone for extended periods. In a
strong uptrend, %R remains above -20 for many bars (persistent overbought). In a strong
downtrend, %R stays below -80 (persistent oversold). This persistence IS the signal — it
means the trend has very strong momentum.

**Use as trend confirmation, NOT as a reversal signal.**

**Playbook conditions (persistent overbought — bullish, hold long):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_williamsr.value",
      "operator": ">",
      "right": "-20",
      "description": "Williams %R in overbought zone"
    },
    {
      "left": "prev.h4_williamsr.value",
      "operator": ">",
      "right": "-20",
      "description": "Previous bar also overbought — persistence confirms trend"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "30",
      "description": "ADX confirms strong trend — do not fade this"
    }
  ]
}
```

**Playbook conditions (end of persistence — potential exit):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_williamsr.value",
      "operator": "<",
      "right": "-20",
      "description": "Williams %R has finally left overbought zone"
    },
    {
      "left": "prev.h4_williamsr.value",
      "operator": ">=",
      "right": "-20",
      "description": "Was overbought on the previous bar (fresh exit)"
    }
  ]
}
```

---

### Pattern 5: Multi-Timeframe Williams %R (Direction + Timing)

**Description:** Use higher-timeframe %R for directional bias and lower-timeframe %R for
entry timing. When both timeframes align, the signal is significantly stronger.

**Playbook conditions (D1 bullish bias + H4 oversold entry):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.d1_williamsr.value",
      "operator": ">",
      "right": "-50",
      "description": "D1 Williams %R above midpoint — bullish daily bias"
    },
    {
      "left": "ind.h4_williamsr.value",
      "operator": "<",
      "right": "-80",
      "description": "H4 Williams %R oversold — pullback within daily uptrend"
    },
    {
      "left": "ind.h4_williamsr.value",
      "operator": ">",
      "right": "prev.h4_williamsr.value",
      "description": "H4 %R turning up — pullback exhaustion"
    }
  ]
}
```

**Playbook conditions (D1 bearish bias + H4 overbought entry):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.d1_williamsr.value",
      "operator": "<",
      "right": "-50",
      "description": "D1 Williams %R below midpoint — bearish daily bias"
    },
    {
      "left": "ind.h4_williamsr.value",
      "operator": ">",
      "right": "-20",
      "description": "H4 Williams %R overbought — rally within daily downtrend"
    },
    {
      "left": "ind.h4_williamsr.value",
      "operator": "<",
      "right": "prev.h4_williamsr.value",
      "description": "H4 %R turning down — rally exhaustion"
    }
  ]
}
```

---

## Combinations

| Combo Indicator     | Purpose                           | Confluence Type      | Example                                      |
|---------------------|-----------------------------------|----------------------|----------------------------------------------|
| + ADX               | Trend regime + pullback timing    | Strategy selector    | ADX > 25 → %R pullback entries; ADX < 25 → %R reversal |
| + ATR               | Volatility-adjusted SL/TP        | Sizing               | %R entry + ATR-based stops                   |
| + EMA (50/200)      | Trend direction + %R timing      | Direction + entry    | Above EMA50 + %R oversold = trend pullback buy|
| + RSI               | Dual momentum confirmation       | Entry confirmation   | %R < -80 + RSI < 30 = strong oversold confluence|
| + Bollinger Bands   | Volatility extremes + momentum   | Dual confirmation    | At lower band + %R < -80 = high-prob reversal|
| + CCI               | Triple oscillator check          | Deep confirmation    | %R + CCI + RSI all oversold = maximum signal |
| + MACD              | Momentum crossover + %R timing   | Entry + confirmation | MACD bullish + %R leaving oversold = buy     |
| + SMC_Structure     | Institutional levels + timing    | Zone + timing        | %R oversold at bullish OB = precision entry  |
| + Stochastic        | Sister oscillator confirmation   | Entry timing         | %R < -80 + Stoch K < 20 = oversold confirmed|

### Williams %R vs Stochastic Comparison

Williams %R and Stochastic are mathematically related but have key differences:

| Feature           | Williams %R         | Stochastic %K/%D           |
|-------------------|---------------------|----------------------------|
| Range             | -100 to 0           | 0 to 100                   |
| Oversold          | Below -80            | Below 20                   |
| Overbought        | Above -20            | Above 80                   |
| Smoothing         | None (raw)           | %D provides smoothing      |
| Speed             | Faster               | Slower (with %D smoothing) |
| False signals     | More (no smoothing)  | Fewer (smoothed)           |
| Best for          | Pullback timing      | Crossover signals          |
| XAUUSD preference | Better for scalping  | Better for swing           |

**When to choose Williams %R over Stochastic:**
- When you need faster response (scalping XAUUSD on M5/M15).
- When you want a single-line oscillator (simpler conditions).
- When your strategy already has enough smoothing from other indicators.

**When to choose Stochastic over Williams %R:**
- When you want K/D crossover signals.
- When you need built-in smoothing to reduce noise.
- When trading on H4/D1 where Stochastic's lag is acceptable.

---

## Position Management

### Dynamic Stop Loss — ATR from %R Signal

When entering on a Williams %R signal, set SL at the recent swing point plus an ATR buffer:

```json
{
  "stop_loss": {
    "type": "dynamic",
    "long_sl_expr": "_price - ind.h4_atr.value * 1.5",
    "short_sl_expr": "_price + ind.h4_atr.value * 1.5",
    "description": "SL at 1.5x ATR from Williams %R entry"
  }
}
```

### %R-Based Trailing Stop

Trail the stop based on Williams %R position. Tighten when %R shows momentum fading:

```json
{
  "trailing_stop": {
    "type": "conditional",
    "rules": [
      {
        "condition": "ind.h4_williamsr.value > -20",
        "long_trail_expr": "_price - ind.h4_atr.value * 2.0",
        "description": "Overbought — wide trail, let the trend run"
      },
      {
        "condition": "ind.h4_williamsr.value > -50",
        "long_trail_expr": "_price - ind.h4_atr.value * 1.5",
        "description": "Above midpoint — standard trail"
      },
      {
        "condition": "ind.h4_williamsr.value < -50",
        "long_trail_expr": "_price - ind.h4_atr.value * 0.75",
        "description": "Below midpoint — tight trail, momentum weakening"
      }
    ]
  }
}
```

### Exit on %R Zone Change

For trend pullback entries, exit when %R reaches the opposite extreme:

```json
{
  "take_profit": {
    "tp1_condition": "ind.h4_williamsr.value > -50",
    "tp1_portion": 0.5,
    "tp1_description": "Take 50% when %R reaches midpoint (-50)",
    "tp2_condition": "ind.h4_williamsr.value > -20",
    "tp2_portion": 0.5,
    "tp2_description": "Take remaining 50% when %R reaches overbought (-20)"
  }
}
```

### Break-Even at Midpoint

Move stop to break-even when %R passes the midpoint, confirming momentum has shifted:

```json
{
  "break_even": {
    "trigger_condition": "ind.h4_williamsr.value > -50",
    "description": "Move SL to entry when Williams %R crosses above -50 (confirms pullback is complete)"
  }
}
```

---

## Pitfalls

1. **Forgetting the negative sign convention.** Williams %R ranges from -100 to 0, NOT
   0 to 100. Oversold is -80 (more negative), overbought is -20 (less negative). Writing
   `%R > 80` when you mean `%R > -20` will never trigger. Always include the minus sign
   in playbook conditions.

2. **Fading Williams %R in strong trends.** When XAUUSD is in a strong uptrend (ADX > 30),
   %R will repeatedly touch the overbought zone (-20 to 0) and stay there. Shorting because
   "%R is overbought" in a strong uptrend is the most common %R mistake. Always check the
   trend first.

3. **Using Williams %R alone without smoothing.** Because %R has no built-in smoothing
   (unlike Stochastic %D), it is noisy and generates many false signals on lower timeframes.
   Always combine with at least one additional indicator for confirmation. RSI or ADX are
   the best companions.

4. **Treating -80 and -20 as hard reversal points.** In a strong gold trend, %R can stay
   below -80 or above -20 for 10+ bars. These levels are zones, not precise reversal
   triggers. Wait for %R to leave the zone (cross back above -80 or below -20) before
   entering.

5. **Over-optimizing the period.** The difference between period 12, 14, and 16 is minimal.
   Do not waste time optimizing. Use 14 for swing trading and 10 for scalping on XAUUSD.
   The edge comes from your strategy logic, not from period fine-tuning.

6. **Ignoring the midpoint (-50).** The -50 level is an underappreciated reference point.
   %R above -50 = bullish half (close is in the upper half of the range). %R below -50 =
   bearish half. Use -50 as a quick directional check.

7. **Redundant combination with Stochastic.** Since Williams %R and Stochastic measure the
   same thing (price position within the range), using both adds minimal new information.
   If you use Williams %R, pair it with a different type of indicator (momentum: RSI/CCI,
   trend: ADX/EMA, volatility: ATR/Bollinger) rather than another range oscillator.

---

## XAUUSD-Specific Notes

### Gold Williams %R Behavioral Patterns

- **Fast overbought/oversold cycling.** On M15/M30, XAUUSD can push %R from oversold to
  overbought in 3-5 bars during London/NY sessions. This fast cycling suits scalping with
  period 10 but generates noise for swing traders (use H4 period 14 instead).
- **Extended zone persistence in gold trends.** During macro gold trends (rate cuts, risk-off),
  %R on H4/D1 can remain in the overbought zone (-20 to 0) for 8-15 bars. This is normal
  for gold and indicates trend strength, not imminent reversal.
- **Asian session neutrality.** During Asian session, %R on H1 tends to hover near -50 as
  gold consolidates. London open often creates the first meaningful push toward -80 or -20.

### XAUUSD Williams %R Thresholds

| Zone              | Standard Levels | XAUUSD Adjusted     | Notes                          |
|-------------------|-----------------|----------------------|--------------------------------|
| Strong overbought | -10 to 0        | -10 to 0             | Identical — extreme is extreme |
| Overbought        | -20 to -10      | -20 to -10           | Standard threshold works       |
| Bullish half      | -50 to -20      | -50 to -20           | Close in upper half of range   |
| Neutral           | -60 to -40      | -55 to -45           | Narrower neutral for gold      |
| Bearish half      | -80 to -50      | -80 to -50           | Close in lower half of range   |
| Oversold          | -90 to -80      | -90 to -80           | Standard threshold works       |
| Strong oversold   | -100 to -90     | -100 to -90          | Identical — extreme is extreme |

### Recommended XAUUSD Williams %R Configurations

**Scalping (M5/M15):**
```json
{
  "id": "m15_williamsr",
  "name": "WilliamsR",
  "timeframe": "M15",
  "params": {"period": 10}
}
```
Use -80/-20 zones. Combine with M15 ATR for SL sizing. Require H1 or H4 trend direction.

**Swing Trading (H4):**
```json
{
  "id": "h4_williamsr",
  "name": "WilliamsR",
  "timeframe": "H4",
  "params": {"period": 14}
}
```
Use -80/-20 zones with confirmation exits. Combine with H4 ADX for regime and H4 ATR for sizing.

**Position Trading (D1):**
```json
{
  "id": "d1_williamsr",
  "name": "WilliamsR",
  "timeframe": "D1",
  "params": {"period": 14}
}
```
Use as a macro directional filter. D1 %R > -50 = bullish bias for all H4 entries.

### Gold Pullback Strategy Template (Williams %R Core)

This is a complete entry template using Williams %R as the primary timing tool for XAUUSD
trend pullback entries:

```json
{
  "name": "XAUUSD Trend Pullback (Williams %R)",
  "direction": "long",
  "entry": {
    "type": "AND",
    "rules": [
      {"left": "ind.d1_williamsr.value", "operator": ">", "right": "-50",
       "description": "D1 %R bullish half — daily uptrend bias"},
      {"left": "ind.h4_adx.adx", "operator": ">", "right": "25",
       "description": "H4 ADX confirms trending market"},
      {"left": "ind.h4_adx.plus_di", "operator": ">", "right": "ind.h4_adx.minus_di",
       "description": "Bullish direction on H4"},
      {"left": "ind.h4_williamsr.value", "operator": "<", "right": "-80",
       "description": "H4 %R oversold — pullback has reached extreme"},
      {"left": "ind.h4_williamsr.value", "operator": ">", "right": "prev.h4_williamsr.value",
       "description": "H4 %R turning up — pullback exhaustion"},
      {"left": "ind.h4_atr.value", "operator": ">", "right": "5.0",
       "description": "Minimum ATR volatility gate"}
    ]
  },
  "stop_loss": "_price - ind.h4_atr.value * 1.5",
  "take_profit_1": {"expr": "_price + ind.h4_atr.value * 2.0", "portion": 0.5},
  "take_profit_2": {"expr": "_price + ind.h4_atr.value * 3.5", "portion": 0.5},
  "break_even_trigger": "ind.h4_williamsr.value > -50"
}
```
