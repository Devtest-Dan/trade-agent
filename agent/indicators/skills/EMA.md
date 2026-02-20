# EMA (Exponential Moving Average) — Playbook Skills

## Overview

The EMA is a trend-following indicator that calculates a weighted average of price, giving
exponentially more weight to recent bars. Unlike the SMA, the EMA reacts faster to price
changes, making it preferred for active trading and momentum strategies.

- **Range:** Unbounded (follows price)
- **Output field:** `value` (e.g., `ind.h4_ema21.value`)
- **Calculation:** EMA = Price * k + EMA_prev * (1 - k), where k = 2 / (period + 1)
- **Key periods:** 9 (fast scalping), 21 (swing), 50 (intermediate trend), 200 (major trend)

The EMA answers: "What is the smoothed trend direction, biased toward recent price action?"
Price above EMA = bullish bias. Price below EMA = bearish bias. The slope of the EMA shows
trend momentum.

---

## When to Use

### Market Conditions
- **Trending markets:** EMA is at its best when markets are directional. Use EMAs to define
  trend direction and as dynamic support/resistance levels for pullback entries.
- **Ranging markets:** EMAs generate whipsaw signals in ranges. Price crosses the EMA
  repeatedly with no follow-through. Avoid EMA crossover signals in flat markets.
- **Breakout confirmation:** Price closing above/below a significant EMA (50 or 200) after
  a consolidation can confirm a breakout.

### Best Timeframes
- **M5/M15 scalping:** EMA(9) and EMA(21) for fast trend direction
- **H1 intraday:** EMA(21) and EMA(50) for trend and dynamic support
- **H4 swing:** EMA(21), EMA(50), and EMA(200) for multi-layer trend analysis
- **D1 position:** EMA(50) and EMA(200) — the "institutional" levels

### XAUUSD Considerations
Gold respects the 21 EMA on H4 remarkably well during trending periods. Institutional
traders and algorithmic systems monitor the 50 and 200 EMAs on H4/D1 for gold positioning.
The 200 EMA on D1 often acts as a major turning point for gold — rallies that fail at the
D1 200 EMA tend to produce significant reversals.

---

## Parameters Guide

| Parameter | Default | Effect of Lower | Effect of Higher | XAUUSD Recommendation |
|-----------|---------|-----------------|------------------|-----------------------|
| period | 20 | Faster response, hugs price closely, more whipsaws | Slower, smoother, more lag, fewer false signals | 9, 21, 50, 200 (see below) |
| applied_price | close | N/A | N/A | close (standard) |

### Period Selection Rules for XAUUSD
| EMA Period | Role | Timeframe | Use Case |
|------------|------|-----------|----------|
| 9 | Ultra-fast trend | M5, M15 | Scalping momentum direction |
| 21 | Fast swing | M15, H1, H4 | Active trend direction, pullback entries |
| 50 | Intermediate | H1, H4, D1 | Trend confirmation, dynamic support/resistance |
| 100 | Long-term bias | H4, D1 | Medium-term trend, less common but useful for gold |
| 200 | Major trend | H4, D1, W1 | Institutional level, trend-defining, golden/death cross |

**Rule of thumb for XAUUSD:** Use 2-3 EMAs simultaneously. A common setup is the 21/50/200
triple EMA stack, which gives you fast trend, intermediate trend, and major trend in one view.

---

## Key Patterns & Setups

### Pattern 1: Trend Direction Filter (Price vs EMA)

**Description:** The simplest and most reliable EMA usage. Price above the EMA = only look
for buys. Price below the EMA = only look for sells. This is a filter, not an entry signal.
Apply this on a higher timeframe (H4 or D1) to filter entries on a lower timeframe.

**Playbook conditions (BUY filter):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": ">", "right": "ind.h4_ema50.value", "description": "Price above H4 50 EMA — bullish trend"},
    {"left": "ind.h4_ema50.value", "operator": ">", "right": "ind.h4_ema200.value", "description": "50 EMA above 200 EMA — trend confirmed"}
  ]
}
```

**Playbook conditions (SELL filter):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": "<", "right": "ind.h4_ema50.value", "description": "Price below H4 50 EMA — bearish trend"},
    {"left": "ind.h4_ema50.value", "operator": "<", "right": "ind.h4_ema200.value", "description": "50 EMA below 200 EMA — downtrend confirmed"}
  ]
}
```

### Pattern 2: EMA Pullback Entry (Dynamic Support/Resistance)

**Description:** In a trending market, price often pulls back to a key EMA and bounces.
The 21 EMA on H4 is the most popular pullback level for XAUUSD swing trading. Wait for
price to touch or slightly penetrate the EMA, then look for a bounce candle.

**Playbook conditions (BUY entry — pullback to 21 EMA):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": ">", "right": "ind.h4_ema50.value", "description": "Price above 50 EMA (uptrend intact)"},
    {"left": "_price", "operator": "<", "right": "ind.h4_ema21.value * 1.002", "description": "Price near or touching 21 EMA (within 0.2%)"},
    {"left": "_price", "operator": ">", "right": "ind.h4_ema21.value * 0.995", "description": "Price not too far below 21 EMA (max 0.5% penetration)"},
    {"left": "ind.h1_rsi.value", "operator": "<", "right": "45", "description": "H1 RSI confirms pullback (not overbought)"}
  ]
}
```

### Pattern 3: EMA Crossover (Fast/Slow)

**Description:** When a faster EMA crosses above a slower EMA, it signals bullish momentum.
When it crosses below, bearish momentum. The classic crossover pairs are 9/21 (fast), 21/50
(medium), and 50/200 (slow/golden cross). Faster pairs give more signals but more whipsaws.
Slower pairs give fewer, higher-quality signals.

**Caution:** EMA crossovers are lagging signals. By the time the cross happens, a significant
portion of the move may have already occurred. Use crossovers as trend confirmation, not as
primary entry triggers.

**Playbook conditions (BUY — 21/50 crossover):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_ema21.value", "operator": ">", "right": "ind.h4_ema50.value", "description": "21 EMA above 50 EMA (bullish cross)"},
    {"left": "prev.h4_ema21.value", "operator": "<", "right": "prev.h4_ema50.value", "description": "21 EMA was below 50 EMA on previous bar (cross just happened)"}
  ]
}
```

**Playbook conditions (SELL — 21/50 crossover):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_ema21.value", "operator": "<", "right": "ind.h4_ema50.value", "description": "21 EMA below 50 EMA (bearish cross)"},
    {"left": "prev.h4_ema21.value", "operator": ">", "right": "prev.h4_ema50.value", "description": "21 EMA was above 50 EMA on previous bar (cross just happened)"}
  ]
}
```

### Pattern 4: EMA Ribbon (Trend Strength)

**Description:** An EMA ribbon uses 3+ EMAs (e.g., 9, 21, 50) stacked in order. When all
EMAs are fanned out in sequence (9 > 21 > 50 for bullish), the trend is strong. When EMAs
converge and tangle, the trend is weakening or transitioning. Use the ribbon state as a
trend strength filter.

**Playbook conditions (BUY — strong uptrend ribbon):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_ema9.value", "operator": ">", "right": "ind.h4_ema21.value", "description": "9 EMA > 21 EMA (fast momentum bullish)"},
    {"left": "ind.h4_ema21.value", "operator": ">", "right": "ind.h4_ema50.value", "description": "21 EMA > 50 EMA (intermediate trend bullish)"},
    {"left": "ind.h4_ema50.value", "operator": ">", "right": "ind.h4_ema200.value", "description": "50 EMA > 200 EMA (major trend bullish)"},
    {"left": "_price", "operator": ">", "right": "ind.h4_ema9.value", "description": "Price above all EMAs"}
  ]
}
```

### Pattern 5: EMA Bounce with Multi-TF Alignment

**Description:** The highest probability EMA trade: price pulls back to a key EMA on the
entry timeframe, while the higher timeframe confirms the trend with its own EMA alignment.
This is the "bread and butter" of XAUUSD trend trading.

**Playbook conditions (BUY — H1 entry with H4 confirmation):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": ">", "right": "ind.h4_ema50.value", "description": "H4: Price above 50 EMA (major trend bullish)"},
    {"left": "ind.h4_ema21.value", "operator": ">", "right": "ind.h4_ema50.value", "description": "H4: 21 > 50 EMA alignment"},
    {"left": "_price", "operator": "<", "right": "ind.h1_ema21.value * 1.001", "description": "H1: Price touching 21 EMA (pullback entry)"},
    {"left": "_price", "operator": ">", "right": "ind.h1_ema50.value", "description": "H1: Still above 50 EMA (trend intact on entry TF)"}
  ]
}
```

---

## Combinations

| Combo | Purpose | Confluence Type | Notes |
|-------|---------|-----------------|-------|
| EMA + RSI | Trend + timing | Filter + Entry | EMA defines direction, RSI times the entry (oversold pullback) |
| EMA + ATR | Dynamic stops | SL/TP sizing | Place SL below EMA minus ATR multiple |
| EMA + MACD | Trend + momentum | Confirmation | EMA crossover confirmed by MACD histogram direction |
| EMA + Bollinger | Trend + volatility | Filter + Entry | Trade Bollinger bounces only in EMA-confirmed trend direction |
| EMA + ADX | Trend + strength | Filter | Only take EMA signals when ADX > 25 (trending market) |
| EMA + SMC_Structure | Trend + institutional | Entry | EMA trend direction + SMC order block for precise entry zone |
| EMA + Stochastic | Trend + momentum | Entry | EMA uptrend + Stochastic oversold = pullback buy |

---

## Position Management

### Dynamic Stop Loss (Below EMA)

Place stop loss below the EMA that price is expected to hold as support. Add an ATR buffer
to avoid being stopped out by normal volatility.

**Stop below 21 EMA with ATR buffer:**
```json
{"expr": "ind.h4_ema21.value - ind.h4_atr.value * 1.0", "description": "SL at 21 EMA minus 1 ATR"}
```

**Stop below 50 EMA with ATR buffer (wider, for swing trades):**
```json
{"expr": "ind.h4_ema50.value - ind.h4_atr.value * 0.5", "description": "SL at 50 EMA minus 0.5 ATR"}
```

### Trailing Stop Using EMA

Trail the stop loss along a key EMA as price advances. This keeps you in the trade during
strong trends while protecting profits.

**Trailing logic:**
- Start: SL at entry EMA (e.g., 21 EMA at entry time)
- As trade progresses: Move SL to current 21 EMA minus small ATR buffer
- Never move SL backward (only forward in trade direction)

**Trailing stop expression:**
```json
{"expr": "ind.h4_ema21.value - ind.h4_atr.value * 0.5", "description": "Trail stop along 21 EMA with 0.5 ATR buffer"}
```

### Take Profit Levels
- **Conservative TP:** Next EMA level (e.g., entered at 50 EMA, TP at 21 EMA of opposite side)
- **Aggressive TP:** 2-3x the distance from entry to SL
- **EMA-based TP for longs:** When price closes below the 9 EMA after being extended

---

## Pitfalls

1. **EMA crossover whipsaws in ranges.** The number one EMA mistake. In a ranging market,
   fast/slow EMA crossovers fire repeatedly with no follow-through. Always verify the market
   is trending (use ADX > 25) before relying on crossover signals.

2. **Using a single EMA in isolation.** One EMA tells you very little. Use at least two EMAs
   (e.g., 21 and 50) to get both trend direction and trend strength via their separation.

3. **Expecting EMAs to work as precise support/resistance.** EMAs are dynamic zones, not exact
   price levels. Price often overshoots an EMA by a few dollars before bouncing. Always add
   an ATR buffer when placing stops at EMA levels.

4. **Ignoring EMA slope.** A flat EMA means no trend, even if price is above it. Check that
   the EMA is sloping in the trade direction. Flat EMAs = ranging market = avoid.

5. **Treating all EMA periods equally.** The 200 EMA on D1 is watched by thousands of
   institutional traders. The 17 EMA on M5 is watched by nobody. Stick to standard periods
   (9, 21, 50, 100, 200) for stronger S/R effects.

6. **Chasing crossovers.** By the time a 50/200 golden cross appears, price may have already
   moved $50-100 on gold. Use the crossover as confirmation of a trend you already identified,
   not as a late entry signal.

7. **Too many EMAs cluttering analysis.** Using 5+ EMAs simultaneously creates analysis
   paralysis. Stick to 2-3 EMAs maximum per strategy.

---

## XAUUSD-Specific Notes

### Gold's Relationship with Key EMAs
- **21 EMA (H4):** The "swing trader's line." XAUUSD respects this EMA during trending
  periods more than most other instruments. Institutional buying/selling often occurs when
  gold tests the H4 21 EMA.
- **50 EMA (H4/D1):** The "institutional bias line." Fund managers reference the 50-day EMA
  for gold positioning decisions. A close above/below this level on D1 often triggers
  institutional flows.
- **200 EMA (D1):** The "bull/bear boundary." Gold above the D1 200 EMA is considered in a
  long-term uptrend by the majority of institutional analysis. Breaks below this level attract
  significant selling. Reclaims above it attract significant buying.

### Session-Based EMA Behavior
- **Asian session:** Price often consolidates around the H1 21 EMA. Good for mean-reversion
  trades between EMA and nearby S/R levels.
- **London session:** EMA breakouts are most reliable during London open (08:00 GMT). A break
  above/below the H1 50 EMA in the first hour of London often sets the tone for the day.
- **New York session:** Gold can gap away from EMAs during major USD data releases. Wait for
  price to retest an EMA level after the initial volatility before entering.

### Recommended XAUUSD EMA Configurations
| Strategy | Timeframe | EMA Setup | Entry Logic |
|----------|-----------|-----------|-------------|
| Scalp momentum | M15 | 9 + 21 | Buy when 9 > 21 and price pulls back to 9 |
| Intraday trend | H1 | 21 + 50 | Buy on 21 EMA bounce when 21 > 50 |
| Swing trend | H4 | 21 + 50 + 200 | Buy on 21 or 50 EMA bounce in full ribbon alignment |
| Position trend | D1 | 50 + 200 | Buy on golden cross or 50 EMA bounce above 200 |

### Price Distance from EMA (Mean Reversion Signal)
When XAUUSD gets too far from a key EMA, it tends to revert. Useful thresholds:
- **H4 21 EMA:** If price is > 2% away, expect a pullback
- **D1 50 EMA:** If price is > 3% away, expect a pullback within 5-10 bars
- **D1 200 EMA:** If price is > 8% away, a major pullback is likely within weeks

**Playbook condition (overextension filter — avoid buying):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "_price", "operator": ">", "right": "ind.h4_ema21.value * 1.02", "description": "Price more than 2% above H4 21 EMA — overextended, avoid new longs"}
  ]
}
```
