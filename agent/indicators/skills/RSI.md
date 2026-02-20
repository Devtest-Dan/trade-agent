# RSI (Relative Strength Index) — Playbook Skills

## Overview

The RSI is a momentum oscillator that measures the speed and magnitude of recent price
changes to evaluate overbought or oversold conditions. It oscillates between 0 and 100.

- **Range:** 0 to 100
- **Key levels:** 30 (oversold), 70 (overbought), 50 (midline/trend bias)
- **Output field:** `value` (e.g., `ind.h4_rsi.value`)
- **Calculation:** RSI = 100 - (100 / (1 + RS)), where RS = avg gain / avg loss over N periods

The RSI answers one question: "How strong is the current move relative to recent history?"
A high RSI means gains dominate recent bars. A low RSI means losses dominate.

---

## When to Use

### Market Conditions
- **Ranging markets:** RSI excels as an overbought/oversold reversal signal when price is
  consolidating inside a defined range. Buy near 30, sell near 70.
- **Trending markets:** Do NOT use 30/70 as reversal signals. Instead, use the shifted
  zones (40-80 for bullish trends, 20-60 for bearish trends) and look for pullback entries
  when RSI returns to the midpoint of the trend zone.
- **Divergence setups:** RSI divergence (price makes new high, RSI makes lower high) works
  in all conditions but requires patience for confirmation.

### Best Timeframes
- **M15 scalping:** RSI(10) for faster signals, combine with H1 trend filter
- **H1 intraday:** RSI(14) standard, good balance of signal quality and frequency
- **H4 swing:** RSI(14) or RSI(21) for fewer but higher-quality signals
- **D1 position:** RSI(14), signals are rare but highly reliable

### XAUUSD Considerations
Gold is driven by safe-haven flows, USD strength, and institutional accumulation. RSI on
gold tends to reach more extreme values during news-driven moves. The 30/70 levels are
frequently breached during London and New York session opens. Use tighter RSI thresholds
(25/75) for XAUUSD reversal entries to filter out false signals during volatility spikes.

---

## Parameters Guide

| Parameter | Default | Effect of Lower | Effect of Higher | XAUUSD Recommendation |
|-----------|---------|-----------------|------------------|-----------------------|
| period | 14 | More sensitive, more signals, more noise. Good for scalping. | Smoother, fewer signals, less noise. Better for swing. | M15: 10, H1: 14, H4: 14, D1: 21 |

### Period Selection Rules for XAUUSD
- **Scalping (M5/M15):** period=10 catches rapid momentum shifts during London/NY sessions
- **Intraday (H1):** period=14 is the universal standard, proven on gold
- **Swing (H4/D1):** period=14 or 21; the 21-period RSI on D1 is excellent for position entries
- **Never go below 7** — too noisy even for gold scalping
- **Never go above 25** — too laggy, you miss entries entirely

---

## Key Patterns & Setups

### Pattern 1: Classic Oversold Bounce (Range Market)

**Description:** RSI drops below 30, then rises back above 30. Price is in a defined range
(not trending). This is a mean-reversion buy signal. Best when price is also near a support
level or a lower Bollinger Band.

**When it works:** Ranging/consolidating XAUUSD during Asian session or low-volatility periods.
**When it fails:** Strong bearish trend — RSI can stay below 30 for many bars.

**Playbook conditions (BUY entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "prev.h1_rsi.value", "operator": "<", "right": "30", "description": "RSI was oversold on previous bar"},
    {"left": "ind.h1_rsi.value", "operator": ">", "right": "30", "description": "RSI crosses back above 30 (recovery)"},
    {"left": "ind.h4_rsi.value", "operator": ">", "right": "40", "description": "H4 RSI not in bearish territory (trend filter)"}
  ]
}
```

### Pattern 2: Classic Overbought Reversal (Range Market)

**Description:** RSI rises above 70, then drops back below 70. This is a mean-reversion
sell signal. Best when price is near resistance.

**Playbook conditions (SELL entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "prev.h1_rsi.value", "operator": ">", "right": "70", "description": "RSI was overbought on previous bar"},
    {"left": "ind.h1_rsi.value", "operator": "<", "right": "70", "description": "RSI drops back below 70 (reversal signal)"},
    {"left": "ind.h4_rsi.value", "operator": "<", "right": "60", "description": "H4 RSI not in strong bullish territory"}
  ]
}
```

### Pattern 3: Bullish Trend Zone Pullback (40-80 Zone)

**Description:** In a confirmed uptrend, RSI oscillates between 40 and 80 instead of 30
and 70. When RSI pulls back to the 40-50 area during an uptrend, it represents a buying
opportunity — the "trend zone pullback." This is one of the most reliable RSI patterns.

**When it works:** XAUUSD in a clear bullish trend (H4 making higher highs/lows).
**Key insight:** If RSI bounces off 40 without reaching 30, the trend is strong.

**Playbook conditions (BUY entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_rsi.value", "operator": ">", "right": "40", "description": "RSI in bullish zone (above 40)"},
    {"left": "ind.h4_rsi.value", "operator": "<", "right": "50", "description": "RSI pulled back to support area of trend zone"},
    {"left": "prev.h4_rsi.value", "operator": "<", "right": "ind.h4_rsi.value", "description": "RSI turning up (current > previous)"},
    {"left": "_price", "operator": ">", "right": "ind.h4_ema50.value", "description": "Price above 50 EMA confirms uptrend"}
  ]
}
```

### Pattern 4: Bearish Trend Zone Pullback (20-60 Zone)

**Description:** Mirror of the bullish zone. In a downtrend, RSI oscillates between 20 and
60. When RSI rallies to 50-60, it is a selling opportunity. If RSI fails to reach 70,
the bear trend is intact.

**Playbook conditions (SELL entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_rsi.value", "operator": "<", "right": "60", "description": "RSI in bearish zone (below 60)"},
    {"left": "ind.h4_rsi.value", "operator": ">", "right": "50", "description": "RSI rallied to resistance area of bear zone"},
    {"left": "prev.h4_rsi.value", "operator": ">", "right": "ind.h4_rsi.value", "description": "RSI turning down (current < previous)"},
    {"left": "_price", "operator": "<", "right": "ind.h4_ema50.value", "description": "Price below 50 EMA confirms downtrend"}
  ]
}
```

### Pattern 5: Multi-Timeframe RSI Alignment

**Description:** When RSI on a higher timeframe (H4/D1) and a lower timeframe (M15/H1) are
both in agreement (both oversold, or both in bullish zone), the probability of a successful
trade is significantly higher. This is a filter pattern, not a standalone entry.

**Playbook conditions (BUY filter — add to any buy entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_rsi.value", "operator": ">", "right": "45", "description": "H4 RSI bullish bias (above midline)"},
    {"left": "ind.h1_rsi.value", "operator": "<", "right": "40", "description": "H1 RSI pulled back (local oversold)"},
    {"left": "ind.h1_rsi.value", "operator": ">", "right": "25", "description": "H1 RSI not extremely oversold (avoid catching knives)"}
  ]
}
```

### Pattern 6: RSI Divergence Concept (Manual/Advanced)

**Description:** Bullish divergence: price makes a lower low, but RSI makes a higher low.
This indicates weakening bearish momentum. Bearish divergence: price makes a higher high,
but RSI makes a lower high. Since the playbook engine compares current values (not swing
structures), divergence is approximated by checking RSI direction vs price direction.

**Approximate divergence filter (bullish):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h1_rsi.value", "operator": ">", "right": "prev.h1_rsi.value", "description": "RSI rising (higher low)"},
    {"left": "_price", "operator": "<", "right": "var.recent_low", "description": "Price at or near recent low"},
    {"left": "ind.h1_rsi.value", "operator": "<", "right": "40", "description": "RSI in lower range (divergence zone)"}
  ]
}
```
**Note:** True divergence detection requires comparing swing points across multiple bars.
The above is a simplified proxy. For stronger divergence signals, combine with SMC_Structure
swing_low detection.

---

## Combinations

| Combo | Purpose | Confluence Type | Notes |
|-------|---------|-----------------|-------|
| RSI + EMA | Trend confirmation | Filter | Use EMA for trend direction, RSI for entry timing |
| RSI + ATR | Volatility-adjusted entries | Filter + SL sizing | Skip RSI signals when ATR is abnormally high (news events) |
| RSI + Bollinger | Mean reversion | Entry | RSI oversold + price at lower Bollinger = strong reversal signal |
| RSI + MACD | Momentum confirmation | Entry | RSI oversold + MACD histogram turning positive = double confirmation |
| RSI + Stochastic | Redundant — avoid | N/A | Both are momentum oscillators; using both adds noise, not value |
| RSI + ADX | Trend strength filter | Filter | Only take RSI trend-zone entries when ADX > 25 (confirmed trend) |
| RSI + SMC_Structure | Institutional zones | Entry + Filter | RSI oversold at an SMC order block = high-probability entry |

---

## Position Management

### Dynamic Stop Loss Using RSI

RSI itself does not produce price levels for stop losses. Instead, use RSI state to adjust
ATR-based stops:

**Tighter stop when RSI is extreme (strong conviction):**
```json
{"expr": "ind.h4_atr.value * 1.0", "description": "Tight stop when RSI signal is strong (below 25 or above 75)"}
```

**Wider stop when RSI is moderate (less conviction):**
```json
{"expr": "ind.h4_atr.value * 2.0", "description": "Wide stop when RSI is in 30-40 zone (weaker signal)"}
```

### RSI-Based Exit Conditions

**Exit long when RSI reaches overbought:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h1_rsi.value", "operator": ">", "right": "75", "description": "RSI overbought — consider taking profit"}
  ]
}
```

**Exit short when RSI reaches oversold:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h1_rsi.value", "operator": "<", "right": "25", "description": "RSI oversold — consider covering short"}
  ]
}
```

### Partial Close Strategy
- Close 50% of position when RSI reaches 65 (for longs) or 35 (for shorts)
- Let remaining 50% ride with a trailing stop
- Exit fully when RSI reaches 75+ (longs) or 25- (shorts)

---

## Pitfalls

1. **Using 30/70 in trending markets.** RSI can stay above 70 for weeks during a strong gold
   rally. Do NOT short just because RSI is overbought in a trend. Use the shifted zones
   (40-80 bullish, 20-60 bearish) instead.

2. **Ignoring the trend.** RSI is a secondary indicator. Always determine the trend first
   (using EMA, ADX, or SMC structure), then use RSI for timing within that trend context.

3. **Over-optimizing the period.** Changing RSI period from 14 to 13 or 15 rarely improves
   results. Stick to 10 for fast TFs and 14 for standard TFs. Curve-fitting RSI periods to
   historical data leads to poor forward performance.

4. **Trading every RSI signal.** Not every cross of 30 or 70 is a trade. Require confluence
   from at least one other indicator or price structure element.

5. **Confusing RSI levels with price levels.** RSI=30 does not mean price is "low." It means
   recent losses outweigh recent gains. Price can keep falling with RSI at 30 if the trend
   is strong enough.

6. **Stacking RSI with Stochastic.** Both measure momentum in similar ways. Using both does
   not add independent confirmation — it just creates redundant signals and false confidence.

7. **Forgetting session context on XAUUSD.** An RSI reading of 70 during the quiet Asian
   session means something very different than RSI 70 during the London/NY overlap. The
   latter often continues higher due to institutional momentum.

---

## XAUUSD-Specific Notes

### Session Behavior
- **Asian session (00:00-08:00 GMT):** RSI signals are more reliable for mean reversion.
  Gold tends to range during this session, so classic 30/70 levels work well.
- **London session (08:00-12:00 GMT):** RSI can spike rapidly. Use RSI as a trend-following
  tool (40-80 zone for buys) rather than a reversal tool during London.
- **New York session (13:00-17:00 GMT):** High volatility from USD news. RSI whipsaws are
  common around major data releases. Consider disabling RSI entries 15 minutes before and
  after major USD news (NFP, CPI, FOMC).

### Gold Volatility Adjustments
- Gold can move $30-50 in a single H4 candle during high-impact events. RSI will hit
  extremes (below 15 or above 85) during these moves. These are NOT reliable reversal
  signals — they are momentum exhaustion points that require additional confirmation.
- During low-volatility periods (ATR below average), RSI works exceptionally well for
  range trading on M15-H1.

### Recommended XAUUSD RSI Configurations
| Strategy | Timeframe | RSI Period | Entry Zone | Target RSI |
|----------|-----------|------------|------------|------------|
| Asian range scalp | M15 | 10 | Buy < 25, Sell > 75 | 50 (midline) |
| London trend follow | H1 | 14 | Buy 40-50 pullback | 70+ |
| Swing trend entry | H4 | 14 | Buy 40-45 in uptrend | 65-70 |
| Position entry | D1 | 21 | Buy < 35 | 55-60 |

### Multi-TF RSI Stack for XAUUSD
The strongest XAUUSD setups occur when:
1. D1 RSI > 50 (bullish bias)
2. H4 RSI between 40-50 (pullback within uptrend)
3. H1 RSI < 35 (local oversold for entry timing)

This triple alignment gives you trend direction (D1), swing context (H4), and precise
entry timing (H1). The reverse applies for short setups.
