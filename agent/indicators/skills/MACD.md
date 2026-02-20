# MACD (Moving Average Convergence Divergence) — Playbook Skills

## Overview

The MACD is a trend-following momentum indicator that shows the relationship between two
EMAs of price. It consists of the MACD line (fast EMA minus slow EMA), the signal line
(EMA of the MACD line), and the histogram (MACD minus signal).

- **Range:** Unbounded (oscillates around zero)
- **Output fields:** `macd` (MACD line), `signal` (signal line)
- **Histogram:** Derived as `ind.<id>.macd - ind.<id>.signal`
- **Default parameters:** fast_ema=12, slow_ema=26, signal=9
- **Key levels:** Zero line (trend polarity), signal line (momentum shifts)

The MACD answers two questions:
1. "Is the short-term momentum aligned with the longer-term trend?" (MACD above/below zero)
2. "Is momentum accelerating or decelerating?" (histogram expanding or contracting)

**Conceptual breakdown:**
- MACD line > 0 = fast EMA above slow EMA = bullish momentum
- MACD line < 0 = fast EMA below slow EMA = bearish momentum
- MACD > signal = momentum accelerating in MACD direction
- MACD < signal = momentum decelerating

---

## When to Use

### Market Conditions
- **Trending markets:** MACD excels at identifying trend direction and momentum strength in
  directional markets. Use the zero line and histogram for trend bias.
- **Trend transitions:** MACD is particularly useful for detecting when a trend is shifting.
  A MACD zero-line cross after an extended move is a strong signal of trend change.
- **Ranging markets:** MACD generates frequent whipsaw crossovers in ranges. The histogram
  oscillates around zero with no clear direction. Avoid MACD signals when ADX < 20.
- **Momentum confirmation:** MACD histogram direction is an excellent secondary confirmation
  for entries triggered by other indicators.

### Best Timeframes
- **M15 scalping:** MACD(8, 17, 9) — faster settings for quicker signals
- **H1 intraday:** MACD(12, 26, 9) — standard settings work well
- **H4 swing:** MACD(12, 26, 9) — the primary MACD timeframe for gold
- **D1 position:** MACD(12, 26, 9) — signals are rare but carry significant weight

### XAUUSD Considerations
Gold's momentum characteristics make MACD particularly effective. Gold tends to move in
sustained trends with well-defined momentum shifts, which is exactly what MACD measures.
The H4 MACD on gold is one of the most reliable trend indicators available. However, during
high-impact USD news events, MACD can give false signals as the rapid price spikes distort
the EMA calculations temporarily.

---

## Parameters Guide

| Parameter | Default | Effect of Lower | Effect of Higher | XAUUSD Recommendation |
|-----------|---------|-----------------|------------------|-----------------------|
| fast_ema | 12 | More sensitive MACD, more crossovers | Slower MACD, fewer crossovers | 8 for scalping, 12 for swing/position |
| slow_ema | 26 | Narrower MACD range, faster zero crosses | Wider MACD range, slower zero crosses | 17 for scalping, 26 for swing/position |
| signal | 9 | Signal line hugs MACD closely, more crossovers | Signal line smoother, fewer/later crossovers | 9 (standard for all) |

### Parameter Sets for XAUUSD
| Strategy | fast_ema | slow_ema | signal | Timeframe | Notes |
|----------|----------|----------|--------|-----------|-------|
| Scalp | 8 | 17 | 9 | M15 | Faster response for short trades |
| Standard | 12 | 26 | 9 | H1, H4 | Universal default, proven on gold |
| Slow trend | 19 | 39 | 9 | D1 | Fewer signals, higher reliability |

**Important:** The ratio between fast and slow EMAs matters more than absolute values.
The standard 12/26 gives a ratio of ~0.46. Keeping the ratio similar (e.g., 8/17 = 0.47)
preserves the MACD's character while adjusting speed.

---

## Key Patterns & Setups

### Pattern 1: Signal Line Crossover (Bullish)

**Description:** The MACD line crosses above the signal line, indicating bullish momentum is
accelerating. This is the most common MACD entry signal. Best when the crossover occurs below
the zero line (early trend reversal) or near the zero line (trend resumption after pullback).

**Playbook conditions (BUY entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": ">", "right": "ind.h4_macd.signal", "description": "MACD above signal line (bullish crossover)"},
    {"left": "prev.h4_macd.macd", "operator": "<", "right": "prev.h4_macd.signal", "description": "MACD was below signal on previous bar (cross just occurred)"}
  ]
}
```

**Enhanced version with trend filter:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": ">", "right": "ind.h4_macd.signal", "description": "MACD bullish crossover"},
    {"left": "prev.h4_macd.macd", "operator": "<", "right": "prev.h4_macd.signal", "description": "Cross just happened"},
    {"left": "_price", "operator": ">", "right": "ind.h4_ema50.value", "description": "Price above 50 EMA (uptrend)"},
    {"left": "ind.h4_macd.macd", "operator": "<", "right": "0", "description": "Crossover below zero line (early reversal — strongest signal)"}
  ]
}
```

### Pattern 2: Signal Line Crossover (Bearish)

**Description:** The MACD line crosses below the signal line, indicating bearish momentum.
Strongest when it occurs above the zero line (early downtrend signal).

**Playbook conditions (SELL entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": "<", "right": "ind.h4_macd.signal", "description": "MACD below signal line (bearish crossover)"},
    {"left": "prev.h4_macd.macd", "operator": ">", "right": "prev.h4_macd.signal", "description": "MACD was above signal on previous bar (cross just occurred)"},
    {"left": "_price", "operator": "<", "right": "ind.h4_ema50.value", "description": "Price below 50 EMA (downtrend confirmed)"}
  ]
}
```

### Pattern 3: Zero Line Cross (Trend Polarity Change)

**Description:** When the MACD line crosses the zero line, the fast EMA has crossed the slow
EMA, confirming a trend direction change. This is a stronger and more reliable signal than a
signal line crossover alone. Zero line crosses on H4/D1 are significant trend events for gold.

**Playbook conditions (BUY — MACD crosses above zero):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": ">", "right": "0", "description": "MACD above zero line (bullish trend)"},
    {"left": "prev.h4_macd.macd", "operator": "<", "right": "0", "description": "MACD was below zero (zero line cross just occurred)"},
    {"left": "ind.h4_macd.macd", "operator": ">", "right": "ind.h4_macd.signal", "description": "Signal line confirms (MACD above signal)"}
  ]
}
```

### Pattern 4: Histogram Momentum (Acceleration/Deceleration)

**Description:** The histogram (MACD minus signal) shows momentum acceleration. When the
histogram is positive and growing, bullish momentum is accelerating. When it starts shrinking,
momentum is decelerating — an early warning of a potential reversal or consolidation.

This is best used as a filter: enter only when the histogram supports your trade direction.

**Playbook conditions (BUY filter — bullish histogram momentum):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd - ind.h4_macd.signal", "operator": ">", "right": "0", "description": "Histogram positive (bullish momentum)"},
    {"left": "ind.h4_macd.macd - ind.h4_macd.signal", "operator": ">", "right": "prev.h4_macd.macd - prev.h4_macd.signal", "description": "Histogram increasing (momentum accelerating)"}
  ]
}
```

**Playbook conditions (EXIT warning — histogram deceleration):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd - ind.h4_macd.signal", "operator": "<", "right": "prev.h4_macd.macd - prev.h4_macd.signal", "description": "Histogram shrinking (momentum fading — tighten stops or take partial profit)"}
  ]
}
```

### Pattern 5: Multi-Timeframe MACD Alignment

**Description:** When MACD is bullish on both the higher timeframe (H4) and the entry
timeframe (H1), the trade probability increases significantly. The H4 MACD provides trend
direction, and the H1 MACD provides entry timing.

**Playbook conditions (BUY — multi-TF alignment):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": ">", "right": "0", "description": "H4 MACD above zero (higher TF bullish trend)"},
    {"left": "ind.h4_macd.macd", "operator": ">", "right": "ind.h4_macd.signal", "description": "H4 MACD above signal (momentum bullish)"},
    {"left": "ind.h1_macd.macd", "operator": ">", "right": "ind.h1_macd.signal", "description": "H1 MACD bullish crossover (entry timing)"},
    {"left": "prev.h1_macd.macd", "operator": "<", "right": "prev.h1_macd.signal", "description": "H1 crossover just occurred"}
  ]
}
```

### Pattern 6: MACD Divergence (Approximate)

**Description:** Bullish MACD divergence: price makes a lower low, but MACD makes a higher
low. This indicates that bearish momentum is weakening even though price is still falling.
Since the playbook engine works with current and previous bar values, true multi-bar
divergence requires approximation.

**Approximate bullish divergence filter:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": ">", "right": "prev.h4_macd.macd", "description": "MACD rising (making higher values)"},
    {"left": "ind.h4_macd.macd", "operator": "<", "right": "0", "description": "MACD still below zero (in bearish territory but improving)"},
    {"left": "ind.h4_rsi.value", "operator": "<", "right": "40", "description": "RSI confirms price weakness (at lows)"}
  ]
}
```

---

## Combinations

| Combo | Purpose | Confluence Type | Notes |
|-------|---------|-----------------|-------|
| MACD + EMA | Momentum + trend | Entry + Filter | MACD crossover with EMA trend confirmation is the gold standard combo |
| MACD + RSI | Momentum + oversold/overbought | Entry + Timing | MACD bullish cross + RSI oversold = strong buy signal |
| MACD + ATR | Momentum + volatility | SL/TP sizing | Enter on MACD signal, size stops with ATR |
| MACD + ADX | Momentum + trend strength | Filter | Only take MACD signals when ADX > 25 (avoid ranging markets) |
| MACD + Bollinger | Momentum + volatility | Entry | MACD bullish + price at lower Bollinger = confluence entry |
| MACD + Stochastic | Momentum + momentum | Entry | MACD above signal + Stochastic turning up from oversold = double momentum confirmation |
| MACD + SMC_Structure | Momentum + institutional | Entry | MACD zero cross + SMC trend confirmation = high-probability setup |
| MACD + SMA(200) | Momentum + major trend | Filter | MACD bullish + price above 200 SMA = position trade filter |

---

## Position Management

### MACD-Based Entry Sizing
- **Strong signal (zero line cross + signal cross):** Full position size
- **Medium signal (signal cross only):** 50-75% position size
- **Weak signal (histogram direction only):** 25-50% or skip

### Dynamic Stop Loss
MACD does not produce price levels directly. Use MACD state to adjust ATR-based stops:

**Tight stop (strong MACD signal):**
```json
{"expr": "ind.h4_atr.value * 1.5", "description": "1.5 ATR stop when MACD gives strong signal (zero cross + signal cross)"}
```

**Wide stop (moderate MACD signal):**
```json
{"expr": "ind.h4_atr.value * 2.5", "description": "2.5 ATR stop when MACD signal is moderate (signal cross only)"}
```

### Exit Rules Using MACD

**Exit on opposite signal line crossover:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": "<", "right": "ind.h4_macd.signal", "description": "MACD bearish crossover — exit long position"}
  ]
}
```

**Partial exit on histogram deceleration:**
When the histogram starts shrinking after being positive, close 50% of the position and
trail the stop on the remaining 50%.

**Full exit on zero line cross against trade:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_macd.macd", "operator": "<", "right": "0", "description": "MACD crossed below zero — trend reversed, exit all"}
  ]
}
```

### Partial Close Strategy
1. Enter on signal line crossover
2. Close 33% when histogram reaches peak and starts declining
3. Close another 33% on opposite signal line crossover
4. Close final 33% on zero line cross against trade direction

---

## Pitfalls

1. **Using MACD in ranging markets.** MACD crossovers in a range produce a string of small
   losses. The MACD will oscillate around zero with frequent signal crosses that go nowhere.
   Always check ADX > 25 before relying on MACD signals.

2. **Treating every signal line crossover as an entry.** Signal line crossovers are frequent,
   especially on lower timeframes. Many are noise. Require additional confluence: EMA trend
   direction, RSI confirmation, or volume analysis.

3. **Ignoring the zero line.** Signal crosses above zero are bullish entries. Signal crosses
   below zero are bearish entries. A bullish signal cross while MACD is deeply negative is
   just a counter-trend bounce — not a reliable buy.

4. **Expecting MACD to work instantly after news.** High-impact USD news causes rapid price
   spikes that distort the MACD calculation. The MACD line will overshoot, and the signal
   line will lag even more than usual. Wait 2-3 bars after news for MACD to normalize.

5. **Confusing MACD value with price direction.** MACD can be positive (above zero) while
   the histogram is declining. This means the trend is still bullish but momentum is fading.
   Understand all three components: MACD line, signal line, and histogram.

6. **Using non-standard parameters without understanding the ratio.** Changing fast_ema to
   5 and slow_ema to 50 creates a MACD that behaves completely differently from standard.
   If you change parameters, maintain the approximate 1:2 ratio between fast and slow.

7. **Double-counting with EMA crossovers.** MACD is literally derived from EMAs. A MACD
   zero-line cross IS an EMA crossover (fast EMA crossing slow EMA). Using both as
   independent confirmation is circular reasoning.

---

## XAUUSD-Specific Notes

### Gold Momentum Characteristics
Gold tends to trend in sustained, momentum-driven moves driven by:
- USD strength/weakness cycles (DXY correlation)
- Safe-haven flows during geopolitical events
- Central bank buying/selling programs
- Inflation expectations

These drivers create the kind of persistent momentum that MACD is designed to capture.
MACD on H4/D1 for gold produces cleaner signals than on most forex pairs because gold's
trends are often fundamentally driven and sustained.

### Session Behavior
- **Asian session:** MACD signals on M15/H1 are less reliable due to low volume. The
  histogram often shows mixed signals during Asian range trading.
- **London session:** MACD signals generated at London open are among the most reliable.
  A bullish MACD cross on H1 at 08:00 GMT often leads to a London session trend.
- **New York session:** MACD can whipsaw during major USD data releases. The best approach
  is to wait for the post-news MACD histogram to establish a clear direction before entering.

### MACD as Entry Trigger vs Filter

**As entry trigger (primary signal):**
Use H1 MACD signal line crossover as the entry trigger, with H4 MACD direction as the filter.
This gives you precise timing on H1 with trend context from H4.

**As filter (secondary confirmation):**
Use MACD histogram direction to confirm entries from other indicators (RSI, Bollinger, SMC).
If MACD histogram is positive and growing, bullish entries from other signals are more likely
to succeed.

### Recommended XAUUSD MACD Configurations
| Strategy | Timeframe | MACD Params | Entry Signal | Filter |
|----------|-----------|-------------|-------------|--------|
| Scalp momentum | M15 | 8, 17, 9 | Signal cross | H1 MACD direction |
| Intraday trend | H1 | 12, 26, 9 | Signal cross below zero | H4 MACD above zero |
| Swing trend | H4 | 12, 26, 9 | Zero line cross | D1 MACD direction |
| Position trend | D1 | 12, 26, 9 | Zero line cross | W1 trend direction |

### MACD Histogram as Trend Strength Gauge
On XAUUSD H4, the histogram provides an excellent gauge of trend strength:
- **Histogram > 0 and growing:** Strong bullish trend — add to longs
- **Histogram > 0 but shrinking:** Bullish trend weakening — tighten stops
- **Histogram crosses to negative:** Trend shift — exit longs
- **Histogram < 0 and growing (more negative):** Strong bearish trend — hold shorts
- **Histogram < 0 but shrinking (less negative):** Bearish trend weakening — tighten stops
