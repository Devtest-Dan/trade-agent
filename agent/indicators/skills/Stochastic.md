# Stochastic Oscillator — Playbook Skills

## Overview

The Stochastic Oscillator is a momentum indicator that compares a security's closing price
to its price range over a specified period. It consists of two lines: %K (the fast line)
and %D (a moving average of %K, the slow/signal line).

- **Range:** 0 to 100
- **Output fields:** `k` (fast line), `d` (slow/signal line)
- **Key levels:** 20 (oversold), 80 (overbought), 50 (midline)
- **Calculation:**
  - %K = ((Close - Lowest Low) / (Highest High - Lowest Low)) * 100
  - %D = SMA of %K over d_period
  - Slowing: SMA applied to raw %K before final output

The Stochastic answers: "Where is the current close relative to the recent price range?"
A reading of 80 means price closed near the top of its recent range. A reading of 20 means
it closed near the bottom.

### Fast vs Slow Stochastic
- **Fast Stochastic:** Raw %K and its SMA (%D). Very choppy, many signals, hard to trade.
- **Slow Stochastic:** Smoothed %K (applying slowing period) and its SMA. This is what
  most platforms and traders use. The `slowing` parameter controls this smoothing.
- **The catalog definition uses slow stochastic** with k_period, d_period, and slowing.

---

## When to Use

### Market Conditions
- **Ranging markets:** Stochastic is at its absolute best in range-bound conditions. When
  price oscillates between support and resistance, Stochastic 80/20 levels produce reliable
  overbought/oversold signals.
- **Trending markets (with caution):** In strong trends, Stochastic can stay overbought (>80)
  or oversold (<20) for extended periods. Do NOT use overbought/oversold reversals in trends.
  Instead, use Stochastic pullbacks: in an uptrend, buy when Stochastic dips to 20-40 and
  turns back up.
- **Choppy/news-driven markets:** Stochastic whipsaws badly during high-volatility news
  events. Avoid using it around FOMC, NFP, and CPI releases.

### Best Timeframes
- **M5/M15 scalping:** Stochastic(5, 3, 3) — fast settings for quick entries in ranges
- **H1 intraday:** Stochastic(14, 3, 3) — standard balanced settings
- **H4 swing:** Stochastic(14, 3, 3) — good for pullback entries within trends
- **D1 position:** Stochastic(14, 5, 5) — slower smoothing for fewer, cleaner signals

### XAUUSD Considerations
Gold frequently enters well-defined ranges, especially during Asian sessions and during
periods between major economic events. Stochastic is particularly effective during these
range-bound phases. However, gold also produces powerful trending moves where Stochastic
remains pinned at extremes — the key is knowing which market regime you are in before
applying Stochastic signals.

---

## Parameters Guide

| Parameter | Default | Effect of Lower | Effect of Higher | XAUUSD Recommendation |
|-----------|---------|-----------------|------------------|-----------------------|
| k_period | 5 | More sensitive, noisier, faster signals | Smoother, fewer signals, more lag | 5 for scalp, 14 for swing |
| d_period | 3 | Signal line closer to K, more crossovers | Signal line smoother, fewer crossovers | 3 (standard) |
| slowing | 3 | Less smoothing, more responsive | More smoothing, fewer whipsaws | 3 (standard) |

### Parameter Sets for XAUUSD
| Strategy | k_period | d_period | slowing | Timeframe | Notes |
|----------|----------|----------|---------|-----------|-------|
| Asian scalp | 5 | 3 | 3 | M15 | Fast signals for range trading during quiet hours |
| London momentum | 8 | 3 | 3 | M15, H1 | Slightly smoother for volatile London session |
| Intraday standard | 14 | 3 | 3 | H1 | Universal standard, works well on gold |
| Swing pullback | 14 | 3 | 3 | H4 | Pullback entries within EMA-confirmed trends |
| Position entry | 14 | 5 | 5 | D1 | Extra smoothing for clean D1 signals |
| Ultra-smooth | 21 | 5 | 5 | D1 | Very few signals, very high reliability |

---

## Key Patterns & Setups

### Pattern 1: K/D Bullish Crossover in Oversold Zone

**Description:** The %K line crosses above the %D line while both are below 20. This is the
classic Stochastic buy signal, indicating that bearish momentum is exhausting and a bounce
is likely. The signal is strongest when price is also at a support level or in a range.

**When it works:** Range-bound markets, pullbacks within uptrends, at support levels.
**When it fails:** Strong downtrends — Stochastic crosses up briefly then falls again.

**Playbook conditions (BUY entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h1_stoch.k", "operator": ">", "right": "ind.h1_stoch.d", "description": "K crossed above D (bullish crossover)"},
    {"left": "prev.h1_stoch.k", "operator": "<", "right": "prev.h1_stoch.d", "description": "K was below D on previous bar (cross just happened)"},
    {"left": "ind.h1_stoch.k", "operator": "<", "right": "30", "description": "Crossover in oversold zone (below 30)"}
  ]
}
```

**Enhanced with trend filter:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h1_stoch.k", "operator": ">", "right": "ind.h1_stoch.d", "description": "K crossed above D (bullish)"},
    {"left": "prev.h1_stoch.k", "operator": "<", "right": "prev.h1_stoch.d", "description": "Cross just occurred"},
    {"left": "ind.h1_stoch.k", "operator": "<", "right": "30", "description": "In oversold zone"},
    {"left": "_price", "operator": ">", "right": "ind.h4_ema50.value", "description": "H4 trend is bullish (above 50 EMA)"}
  ]
}
```

### Pattern 2: K/D Bearish Crossover in Overbought Zone

**Description:** The %K line crosses below the %D line while both are above 80. This signals
that bullish momentum is exhausting. Strongest when price is at resistance.

**Playbook conditions (SELL entry):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h1_stoch.k", "operator": "<", "right": "ind.h1_stoch.d", "description": "K crossed below D (bearish crossover)"},
    {"left": "prev.h1_stoch.k", "operator": ">", "right": "prev.h1_stoch.d", "description": "K was above D on previous bar (cross just happened)"},
    {"left": "ind.h1_stoch.k", "operator": ">", "right": "70", "description": "Crossover in overbought zone (above 70)"},
    {"left": "_price", "operator": "<", "right": "ind.h4_ema50.value", "description": "H4 trend is bearish (below 50 EMA)"}
  ]
}
```

### Pattern 3: Stochastic Trend Pullback (Uptrend)

**Description:** In a confirmed uptrend, use Stochastic not as a reversal indicator but as a
pullback timer. When Stochastic dips below 30-40 during an uptrend, wait for K to cross back
above D and enter long. This catches the resumption of the trend after a temporary pullback.

**Key insight:** In uptrends, Stochastic rarely goes below 20. If it reaches 30-40 and turns
up, that is the "trend pullback zone." Do not wait for 20 — you will miss the entry.

**Playbook conditions (BUY — trend pullback):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "ind.h4_stoch.d", "description": "K above D (turning up)"},
    {"left": "prev.h4_stoch.k", "operator": "<", "right": "prev.h4_stoch.d", "description": "K was below D (pullback was active)"},
    {"left": "ind.h4_stoch.k", "operator": "<", "right": "50", "description": "K in lower half (pullback zone, not overbought)"},
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "20", "description": "K above 20 (not extreme — supports trend continuation)"},
    {"left": "_price", "operator": ">", "right": "ind.h4_ema50.value", "description": "Price above 50 EMA (uptrend confirmed)"},
    {"left": "ind.h4_ema21.value", "operator": ">", "right": "ind.h4_ema50.value", "description": "EMAs in bullish alignment"}
  ]
}
```

### Pattern 4: Double Bottom in Stochastic (Bullish)

**Description:** Stochastic makes two dips into oversold territory (<20) within a short
period, and the second dip holds above the first dip's low. This forms a "double bottom"
in the oscillator, suggesting a reversal. Approximate this by checking that current K is
oversold, rising, and above its recent low.

**Playbook conditions (BUY — double bottom approximation):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_stoch.k", "operator": "<", "right": "25", "description": "K in oversold area"},
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "prev.h4_stoch.k", "description": "K turning up (rising from dip)"},
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "ind.h4_stoch.d", "description": "K crossed above D (momentum shifting)"},
    {"left": "ind.h4_rsi.value", "operator": "<", "right": "35", "description": "RSI confirms oversold condition (multi-indicator confluence)"}
  ]
}
```

### Pattern 5: Stochastic Divergence (Approximate)

**Description:** Bullish divergence: price makes a lower low but Stochastic K makes a higher
low. This signals weakening bearish momentum. Bearish divergence: price makes a higher high
but K makes a lower high. The playbook engine can approximate this by comparing current vs
previous values.

**Approximate bullish divergence:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "prev.h4_stoch.k", "description": "K rising (higher low pattern)"},
    {"left": "ind.h4_stoch.k", "operator": "<", "right": "30", "description": "K in lower range (divergence is meaningful here)"},
    {"left": "_price", "operator": "<", "right": "var.recent_low", "description": "Price at or near lows (needed for divergence)"},
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "ind.h4_stoch.d", "description": "K above D (momentum turning)"}
  ]
}
```

### Pattern 6: Multi-Timeframe Stochastic Alignment

**Description:** When the higher timeframe Stochastic confirms the direction and the lower
timeframe provides the entry signal, the trade probability increases. Use H4 Stochastic for
direction and H1 for timing.

**Playbook conditions (BUY — multi-TF alignment):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "ind.h4_stoch.d", "description": "H4 Stochastic bullish (K above D)"},
    {"left": "ind.h4_stoch.k", "operator": "<", "right": "70", "description": "H4 K not overbought (room to run)"},
    {"left": "ind.h1_stoch.k", "operator": ">", "right": "ind.h1_stoch.d", "description": "H1 K crosses above D (entry signal)"},
    {"left": "prev.h1_stoch.k", "operator": "<", "right": "prev.h1_stoch.d", "description": "H1 cross just occurred"},
    {"left": "ind.h1_stoch.k", "operator": "<", "right": "40", "description": "H1 K in lower zone (pullback entry)"}
  ]
}
```

---

## Combinations

| Combo | Purpose | Confluence Type | Notes |
|-------|---------|-----------------|-------|
| Stochastic + EMA | Timing + trend | Entry + Filter | Stochastic oversold + EMA uptrend = trend pullback buy |
| Stochastic + ATR | Timing + volatility | SL sizing | Enter on Stoch signal, size stop with ATR |
| Stochastic + Bollinger | Timing + volatility | Entry | Stoch oversold + price at lower BB = strong mean reversion |
| Stochastic + MACD | Momentum + momentum | Entry | Stoch oversold turn + MACD histogram positive = double confirmation |
| Stochastic + ADX | Timing + trend strength | Filter | Stoch signals only when ADX < 25 (range) for reversals, or ADX > 25 (trend) for pullbacks |
| Stochastic + RSI | Redundant — use carefully | N/A | Both are momentum oscillators. Only use if on different TFs (e.g., RSI H4, Stoch H1) |
| Stochastic + SMC_Structure | Timing + institutional | Entry | Stoch oversold at SMC order block = high-probability entry |
| Stochastic + SMA(200) | Timing + major trend | Filter | Only take Stoch buys above D1 200 SMA |

---

## Position Management

### Dynamic Stop Loss

Stochastic does not produce price levels directly. Use Stochastic state to determine
conviction level and adjust ATR-based stops accordingly.

**High conviction (K < 15, deep oversold crossover):**
```json
{"expr": "ind.h4_atr.value * 1.5", "description": "Tight 1.5 ATR stop — deep oversold gives high conviction"}
```

**Medium conviction (K between 20-30, standard oversold):**
```json
{"expr": "ind.h4_atr.value * 2.0", "description": "Standard 2 ATR stop — normal oversold crossover"}
```

**Lower conviction (K between 30-40, trend pullback):**
```json
{"expr": "ind.h4_atr.value * 2.5", "description": "Wider 2.5 ATR stop — shallow pullback needs more room"}
```

### Exit Rules Using Stochastic

**Exit long when K enters overbought and crosses below D:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "75", "description": "K in overbought zone"},
    {"left": "ind.h4_stoch.k", "operator": "<", "right": "ind.h4_stoch.d", "description": "K crossed below D (momentum fading)"}
  ]
}
```

**Exit short when K enters oversold and crosses above D:**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_stoch.k", "operator": "<", "right": "25", "description": "K in oversold zone"},
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "ind.h4_stoch.d", "description": "K crossed above D (bearish momentum fading)"}
  ]
}
```

### Partial Close Strategy
1. Enter on K/D crossover in oversold zone
2. Close 50% when K reaches 50 (midline — halfway to target)
3. Close remaining 50% when K reaches 75-80 (overbought zone)
4. If K fails to reach 50 and crosses back below D, exit everything

### Trailing Strategy
In trending trades (not range trades), once Stochastic reaches overbought (for longs):
- Do NOT exit immediately — trend may continue
- Instead, wait for K to cross below D in the overbought zone
- Move stop to breakeven when K first crosses 80
- Trail stop using EMA-based trailing (Stochastic is not ideal for trailing)

---

## Pitfalls

1. **Using overbought/oversold as reversal signals in trending markets.** This is the number
   one Stochastic mistake. In a strong uptrend, Stochastic can stay above 80 for dozens of
   bars. Selling every time K crosses above 80 produces a string of losing shorts. Always
   determine market regime (trend vs range) before applying Stochastic.

2. **Ignoring the D line.** Many traders watch only K. The D line provides crucial
   confirmation. A K line dipping below 20 means nothing until K crosses back above D. The
   crossover is the signal, not the level alone.

3. **Trading K/D crossovers in the middle zone (40-60).** Crossovers in the middle of the
   Stochastic range (40-60) are mostly noise. They indicate indecision, not a directional
   signal. Only trade crossovers in the extreme zones (below 30 or above 70).

4. **Using fast stochastic (slowing=1).** Raw fast stochastic is extremely noisy and produces
   many false signals. Always use slow stochastic (slowing >= 3) for trading decisions.

5. **Stacking Stochastic with RSI for "double confirmation."** Both indicators measure
   momentum relative to recent range. They are highly correlated and do not provide
   independent confirmation. If you want double confirmation, combine Stochastic (momentum)
   with an EMA (trend) or ATR (volatility) — different indicator types.

6. **Not adjusting for XAUUSD volatility.** Gold's volatility means Stochastic can whipsaw
   through 20 and 80 zones rapidly during news. If ATR is significantly above its 20-period
   average, consider widening the zones to 15/85 or simply avoiding Stochastic entries.

7. **Expecting Stochastic to work the same on all timeframes.** M5 Stochastic is very noisy
   and produces many false signals on gold. H4 Stochastic is much cleaner. Always prefer
   higher timeframe Stochastic readings or use lower TF only with higher TF confirmation.

8. **Entering immediately on the K/D cross without waiting for bar close.** Within a bar,
   K and D can cross and uncross multiple times. Always wait for the bar to close before
   confirming a crossover signal.

---

## XAUUSD-Specific Notes

### Gold's Stochastic Behavior

Gold has distinct Stochastic characteristics based on its market microstructure:

**In uptrends:**
- Stochastic on H4 typically oscillates between 30 and 95
- It rarely touches 20 during strong gold rallies
- The "oversold" pullback zone in gold uptrends is 30-40, not the traditional 20
- Waiting for Stochastic to reach 20 in a gold uptrend means missing most pullback entries

**In downtrends:**
- Stochastic on H4 oscillates between 5 and 70
- It rarely reaches 80 during gold selloffs
- The "overbought" rally zone in gold downtrends is 60-70, not the traditional 80

**In ranges:**
- Classic 20/80 levels work well during Asian session ranges
- Stochastic is highly effective for gold range trading on M15/H1 during low-volatility periods

### Session-Specific Stochastic Behavior

- **Asian session (00:00-08:00 GMT):** Best time for Stochastic range trading on gold.
  Price tends to consolidate, and Stochastic 20/80 reversals are reliable. Use
  Stochastic(5, 3, 3) on M15 for Asian session scalping.

- **London session (08:00-12:00 GMT):** Stochastic signals at London open can be tricky.
  The initial move often pushes Stochastic to an extreme, but the subsequent pullback
  provides the real entry. Wait for the first pullback rather than fading the initial move.

- **New York session (13:00-17:00 GMT):** Stochastic whipsaws during major USD data. Avoid
  Stochastic entries 15 minutes before and 30 minutes after NFP, CPI, and FOMC. After the
  dust settles, Stochastic can provide excellent continuation entries.

- **London/NY overlap (13:00-16:00 GMT):** Highest gold volume period. Stochastic crossovers
  during this overlap carry more weight because they are backed by genuine volume.

### Recommended XAUUSD Stochastic Configurations
| Strategy | Timeframe | K | D | Slowing | Entry Zone | Exit Zone |
|----------|-----------|---|---|---------|------------|-----------|
| Asian range scalp | M15 | 5 | 3 | 3 | Buy < 20, Sell > 80 | Midline (50) |
| London pullback | H1 | 14 | 3 | 3 | Buy 25-35 (in uptrend) | 70-75 |
| Swing pullback | H4 | 14 | 3 | 3 | Buy 30-40 (in uptrend) | 75-85 |
| Position entry | D1 | 14 | 5 | 5 | Buy < 25 | 70+ |

### Multi-TF Stochastic Stack for XAUUSD
The strongest Stochastic setups on gold occur when:

**For buys:**
1. D1 Stochastic K > 50 and K > D (bullish bias)
2. H4 Stochastic K between 25-40 (pullback zone in uptrend)
3. H1 Stochastic K crosses above D below 30 (entry trigger)

**For sells:**
1. D1 Stochastic K < 50 and K < D (bearish bias)
2. H4 Stochastic K between 60-75 (rally zone in downtrend)
3. H1 Stochastic K crosses below D above 70 (entry trigger)

### Stochastic + SMC Confluence (Gold-Specific)
One of the highest probability setups on gold combines Stochastic with Smart Money Concepts:
- Price reaches an SMC order block (supply/demand zone)
- Stochastic confirms with an oversold/overbought crossover at that zone
- H4 trend (from SMC_Structure indicator) confirms the direction

**Playbook example (BUY — Stochastic + SMC OB):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_stoch.k", "operator": ">", "right": "ind.h4_stoch.d", "description": "H4 Stochastic bullish crossover"},
    {"left": "ind.h4_stoch.k", "operator": "<", "right": "35", "description": "Crossover in oversold/pullback zone"},
    {"left": "ind.h4_obfvg.ob_type", "operator": "==", "right": "1", "description": "Bullish order block present"},
    {"left": "_price", "operator": ">", "right": "ind.h4_obfvg.ob_lower", "description": "Price within OB zone (above lower boundary)"},
    {"left": "_price", "operator": "<", "right": "ind.h4_obfvg.ob_upper", "description": "Price within OB zone (below upper boundary)"}
  ]
}
```

### Volatility-Adjusted Zones
When XAUUSD volatility is high (ATR above 1.5x its 20-period average), widen Stochastic
zones to reduce false signals:
- Standard zones: 20/80
- High volatility zones: 15/85
- Extreme volatility (news): 10/90 or avoid Stochastic entirely

**Playbook filter (high volatility warning):**
```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_atr.value", "operator": "<", "right": "ind.h4_atr.value * 1.5", "description": "ATR not abnormally elevated (avoid Stochastic in extreme volatility)"}
  ]
}
```
**Note:** The above is a conceptual filter. In practice, compare current ATR to a baseline
(e.g., a longer-period ATR or a fixed dollar threshold for gold, such as ATR < $15 on H4).
