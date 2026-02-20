# SMA (Simple Moving Average) — Playbook Skills

## Overview

The SMA calculates the arithmetic mean of price over N periods, giving equal weight to every
bar in the lookback window. It is the most widely used moving average and the foundation of
many institutional trading systems.

- **Range:** Unbounded (follows price)
- **Output field:** `value` (e.g., `ind.d1_sma200.value`)
- **Calculation:** SMA = (P1 + P2 + ... + Pn) / N
- **Key periods:** 20 (short-term), 50 (intermediate), 100 (medium-term), 200 (long-term)

The SMA answers: "What is the average price over the last N bars?" Because it weights all
bars equally, the SMA is smoother and less reactive than the EMA. This makes it better for
identifying major trend levels that institutions watch, but worse for fast entry timing.

### SMA vs EMA — When to Use Which
| Aspect | SMA | EMA |
|--------|-----|-----|
| Reactivity | Slow — lags price more | Fast — responds quickly to recent price |
| Whipsaws | Fewer false crosses | More false crosses in ranges |
| Institutional use | Preferred for 50/100/200-period levels | Preferred for 9/21-period levels |
| Best for | Major trend levels, golden/death cross | Dynamic S/R, pullback entries |
| XAUUSD use | D1 50/200 SMA for institutional bias | H1/H4 21/50 EMA for active trading |

**Rule of thumb:** Use SMA for the slow, institutional-grade levels (50, 100, 200 on D1/W1).
Use EMA for the faster, active trading levels (9, 21, 50 on M15/H1/H4).

---

## When to Use

### Market Conditions
- **Long-term trend identification:** The 200 SMA on D1 is the single most watched level in
  global markets, including gold. Price above = bull market, price below = bear market.
- **Major crossover signals:** The 50/200 SMA golden cross and death cross are major
  institutional signals that can trigger large capital flows in gold.
- **Mean reversion:** Price distance from the 50 or 200 SMA can be used as a mean-reversion
  filter — when price is too far from the SMA, a pullback is probable.
- **Ranging markets:** Avoid SMA-based entries in ranges. The SMA flattens and price chops
  above and below it repeatedly.

### Best Timeframes
- **H4:** 50 SMA and 200 SMA for swing trade bias
- **D1:** The primary timeframe for SMA analysis. The D1 50 and 200 SMA are the most
  important levels for gold.
- **W1:** 50 SMA for macro trend — rarely touched but extremely significant when tested

### XAUUSD Considerations
The 200 SMA on the D1 chart is arguably the single most important technical level for gold.
Central bank analysts, fund managers, and algorithmic trading systems reference it for
strategic positioning. When gold crosses above or below the D1 200 SMA, it generates
headlines and triggers significant order flow.

---

## Parameters Guide

| Parameter | Default | Effect of Lower | Effect of Higher | XAUUSD Recommendation |
|-----------|---------|-----------------|------------------|-----------------------|
| period | 20 | More reactive, less institutional significance | Smoother, more institutional significance, more lag | 50, 100, 200 (see below) |
| applied_price | close | N/A | N/A | close (standard) |

### Period Selection for XAUUSD
| SMA Period | Significance | Timeframe | What It Represents |
|------------|-------------|-----------|-------------------|
| 20 | Short-term average | H1, H4 | ~1 trading week on H4, ~1 day on H1 |
| 50 | Intermediate trend | H4, D1 | ~2.5 months on D1, ~2 weeks on H4 |
| 100 | Medium-term trend | D1 | ~5 months of data — half a year bias |
| 200 | Long-term trend | D1, W1 | ~10 months on D1, ~4 years on W1 |

**XAUUSD priority:** Focus on 50 and 200 SMA on D1. These are the levels that move markets.

---

## Key Patterns & Setups

### Pattern 1: Golden Cross (50 SMA Crosses Above 200 SMA)

**Description:** When the 50 SMA crosses above the 200 SMA, it signals a major bullish
trend shift. This is one of the most-followed signals in all of financial markets. For gold,
a golden cross on D1 often precedes rallies of $100-300 over weeks to months.

**Caveat:** The golden cross is a lagging signal. By the time it occurs, price has already
moved significantly. Use it as a trend confirmation for position trades, not as a precise
entry trigger. It works best when combined with a pullback entry on a lower timeframe.

**Playbook conditions (BUY — golden cross confirmation):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.d1_sma50.value", "operator": ">", "right": "ind.d1_sma200.value", "description": "D1 golden cross: 50 SMA above 200 SMA"},
    {"left": "_price", "operator": ">", "right": "ind.d1_sma50.value", "description": "Price above both SMAs (trend active)"}
  ]
}
```

### Pattern 2: Death Cross (50 SMA Crosses Below 200 SMA)

**Description:** The inverse of the golden cross. When the 50 SMA crosses below the 200 SMA,
it signals a major bearish trend shift. For gold, death crosses have historically preceded
extended consolidation or decline periods.

**Playbook conditions (SELL — death cross confirmation):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.d1_sma50.value", "operator": "<", "right": "ind.d1_sma200.value", "description": "D1 death cross: 50 SMA below 200 SMA"},
    {"left": "_price", "operator": "<", "right": "ind.d1_sma50.value", "description": "Price below both SMAs (downtrend active)"}
  ]
}
```

### Pattern 3: Price Bounce Off 200 SMA (Major Support/Resistance)

**Description:** The 200 SMA on D1 acts as a major support in uptrends and resistance in
downtrends. When price tests this level and bounces, it is a high-probability entry. This
level is so widely watched that institutional buy/sell orders cluster around it.

**Playbook conditions (BUY — bounce off D1 200 SMA support):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": ">", "right": "ind.d1_sma200.value * 0.995", "description": "Price near 200 SMA (within 0.5%)"},
    {"left": "_price", "operator": "<", "right": "ind.d1_sma200.value * 1.01", "description": "Price not too far above 200 SMA (still in bounce zone)"},
    {"left": "ind.h4_rsi.value", "operator": "<", "right": "40", "description": "H4 RSI showing oversold/pullback conditions"},
    {"left": "ind.d1_sma50.value", "operator": ">", "right": "ind.d1_sma200.value", "description": "50 SMA still above 200 SMA (uptrend intact)"}
  ]
}
```

### Pattern 4: Mean Reversion — Price Distance from SMA

**Description:** When price gets significantly far from a key SMA, it tends to revert back
toward the average. This is not a standalone entry signal, but a powerful filter. Avoid
entering trend-continuation trades when price is overextended from the SMA. Conversely,
look for reversal opportunities when distance is extreme.

**Key distances for XAUUSD:**
- D1 50 SMA: > 3% away = overextended
- D1 200 SMA: > 8% away = strongly overextended
- H4 50 SMA: > 2% away = short-term overextended

**Playbook conditions (filter — avoid buying when overextended):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": "<", "right": "ind.d1_sma50.value * 1.03", "description": "Price less than 3% above D1 50 SMA (not overextended)"}
  ]
}
```

**Playbook conditions (mean reversion sell — price extremely above SMA):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": ">", "right": "ind.d1_sma50.value * 1.05", "description": "Price more than 5% above D1 50 SMA — extreme overextension"},
    {"left": "ind.h4_rsi.value", "operator": ">", "right": "70", "description": "H4 RSI overbought confirms overextension"},
    {"left": "ind.d1_sma50.value", "operator": ">", "right": "ind.d1_sma200.value", "description": "Long-term trend still bullish (this is a pullback trade, not a trend reversal)"}
  ]
}
```

### Pattern 5: SMA as Trailing Profit Target

**Description:** After entering a counter-trend or mean-reversion trade, use the SMA as
the profit target. For example, after a pullback buy at an oversold level, target the 50 SMA
as the mean-reversion destination.

**Exit condition (close long at SMA):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": ">", "right": "ind.h4_sma50.value * 0.998", "description": "Price reached 50 SMA level (take profit zone)"}
  ]
}
```

---

## Combinations

| Combo | Purpose | Confluence Type | Notes |
|-------|---------|-----------------|-------|
| SMA + EMA | Institutional + active levels | Filter + Entry | SMA for D1 bias, EMA for H1/H4 entries |
| SMA + RSI | Trend level + momentum | Filter + Entry | Buy at 200 SMA bounce when RSI oversold |
| SMA + ATR | Level + volatility buffer | SL sizing | Place SL below SMA minus ATR to avoid normal volatility |
| SMA + MACD | Trend + momentum direction | Confirmation | Golden cross + MACD bullish = strong confirmation |
| SMA + ADX | Trend level + trend strength | Filter | Only take SMA signals when ADX confirms trending (> 25) |
| SMA + Bollinger | Mean reversion | Entry + Target | Bollinger lower band touch + price near SMA = reversion entry |
| SMA + SMC_Structure | Institutional + smart money | Entry | D1 200 SMA that aligns with an SMC order block = very high probability |

---

## Position Management

### Dynamic Stop Loss

For SMA-based trades, the stop is placed beyond the SMA with a volatility buffer.

**Stop below D1 200 SMA (position trade):**
```json
{"expr": "ind.d1_sma200.value - ind.d1_atr.value * 2.0", "description": "SL below D1 200 SMA with 2 ATR buffer — wide stop for position trade"}
```

**Stop below H4 50 SMA (swing trade):**
```json
{"expr": "ind.h4_sma50.value - ind.h4_atr.value * 1.5", "description": "SL below H4 50 SMA with 1.5 ATR buffer"}
```

### Take Profit Using SMA Levels

Use higher SMA levels as profit targets:
- Entered at 200 SMA bounce -> TP at 50 SMA (price should revert to the faster average)
- Entered at 50 SMA bounce -> TP at 20 SMA or previous swing high

**TP expression:**
```json
{"expr": "ind.d1_sma50.value", "description": "Take profit at D1 50 SMA (mean reversion target)"}
```

### Trailing Stop
SMAs are too slow for active trailing on most timeframes. For SMA-based position trades,
trail using the H4 50 EMA instead, or move the stop to breakeven once price reaches the
next SMA level.

---

## Pitfalls

1. **Using SMA for fast entries.** The SMA is too laggy for quick entries on M15 or H1. Use
   EMA for those timeframes. Reserve SMA for D1/W1 strategic levels.

2. **Trading golden/death crosses as instant signals.** These are confirmation signals, not
   entries. A golden cross tells you the trend has shifted, but price may have already moved
   $100+. Wait for a pullback after the cross for a better entry.

3. **Ignoring that SMA drops old data abruptly.** Unlike the EMA (which slowly fades old
   data), the SMA drops a bar from the calculation when it exits the lookback window. This
   can cause the SMA to jump when a large price bar exits the window, even if current price
   is flat.

4. **Expecting precise bounces at SMA levels.** The 200 SMA is a zone, not a line. Price may
   penetrate by $5-20 on gold before bouncing. Always use an ATR buffer for stops placed at
   SMA levels.

5. **Dismissing the 200 SMA.** Some traders think the 200 SMA is "too slow to be useful."
   On gold, it is the single most important technical level. Ignoring it means ignoring
   institutional behavior.

6. **Using SMA periods that nobody watches.** An 83-period or 137-period SMA has no
   institutional significance. Stick to standard periods: 20, 50, 100, 200. These are the
   levels where institutional orders cluster.

7. **Comparing SMA across different instruments without context.** The 200 SMA on gold
   operates differently than on forex pairs or equities due to gold's unique market structure
   and volatility profile. Always calibrate expectations to gold's behavior.

---

## XAUUSD-Specific Notes

### Institutional Behavior Around Key SMAs

**D1 200 SMA:**
- Central banks and sovereign wealth funds use the 200-day SMA as a benchmark for gold
  allocation decisions. When gold is above the 200 SMA, they tend to be net buyers. Below
  it, they reduce exposure.
- Algorithmic trading systems place large orders at the 200 SMA. You will often see price
  spike down to the 200 SMA, trigger stops, then reverse sharply as institutional bids fill.
- When gold breaks below the D1 200 SMA for the first time in months, expect 1-3 retests
  of the SMA as resistance before the downtrend accelerates.

**D1 50 SMA:**
- The 50 SMA on D1 is the "intermediate-term sentiment line." Fund managers reference it in
  quarterly reports. A close above it is bullish. A close below it shifts sentiment bearish.
- During strong uptrends, the D1 50 SMA acts as a "buy the dip" level. Gold will pull back
  to it, consolidate for 2-5 days, then resume the uptrend.

**D1 100 SMA:**
- Less commonly discussed but important for gold. The 100 SMA often acts as a "last line of
  defense" between the 50 and 200 SMAs during corrective phases.

### Session Behavior
- **London open:** If gold is testing a major SMA (50 or 200 on D1), expect increased
  volume and volatility at London open as institutional traders place orders around the level.
- **New York session:** Major SMA levels are most respected during NY hours when the largest
  gold futures contracts trade.
- **Asian session:** SMAs are less relevant during Asian hours due to lower volume. Price may
  drift through an SMA without institutional response.

### SMA Levels as Confluence Zones
The highest probability XAUUSD setups occur when a major SMA aligns with other levels:
- D1 200 SMA + SMC order block = very strong support/resistance
- D1 50 SMA + round number ($1900, $2000, $2100) = psychological + technical confluence
- D1 200 SMA + Fibonacci 61.8% retracement = textbook confluence entry

### Historical Gold Behavior After Golden/Death Crosses
| Signal | Average Move After | Duration | Win Rate |
|--------|-------------------|----------|----------|
| D1 Golden Cross | +$80-150 | 2-4 months | ~65% |
| D1 Death Cross | -$50-100 | 1-3 months | ~55% |
| W1 Golden Cross | +$200-400 | 6-12 months | ~70% |

**Note:** These are approximate ranges based on historical gold behavior. They are not
guarantees. Use as context, not as predictions.

### Recommended XAUUSD SMA Configurations
| Strategy | Timeframe | SMA Setup | Entry Logic |
|----------|-----------|-----------|-------------|
| Position trend | D1 | 50 + 200 | Buy on golden cross, enter on H4 pullback |
| Institutional bounce | D1 | 200 | Buy on 200 SMA test with RSI < 35 |
| Mean reversion | D1 | 50 | Sell when price > 5% above 50 SMA |
| Macro trend filter | W1 | 50 | Only take D1 longs when price above W1 50 SMA |
