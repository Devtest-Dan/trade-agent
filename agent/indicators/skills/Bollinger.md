# Bollinger Bands — Playbook Skills

## Overview

Bollinger Bands are a volatility-based envelope indicator that places an upper and lower band
at N standard deviations above and below a simple moving average (the middle band). The bands
dynamically expand during high volatility and contract during low volatility, making them one
of the most versatile indicators for both trend-following and mean-reversion strategies.

**Indicator ID format:** `ind.<tf>_bollinger` (e.g., `ind.h4_bollinger`, `ind.h1_bollinger`)

**Outputs:**
| Field    | Access Expression              | Description                        |
|----------|--------------------------------|------------------------------------|
| upper    | `ind.h4_bollinger.upper`       | Upper band (SMA + N * StdDev)      |
| middle   | `ind.h4_bollinger.middle`      | Middle band (SMA)                  |
| lower    | `ind.h4_bollinger.lower`       | Lower band (SMA - N * StdDev)      |

**Derived concepts (compute in conditions):**
- **Bandwidth:** `(ind.h4_bollinger.upper - ind.h4_bollinger.lower) / ind.h4_bollinger.middle`
  Measures relative band width. Low bandwidth = squeeze. High bandwidth = expansion.
- **%B:** `(_price - ind.h4_bollinger.lower) / (ind.h4_bollinger.upper - ind.h4_bollinger.lower)`
  Shows where price sits within the bands. 0 = at lower band, 1 = at upper band, 0.5 = at middle.

---

## When to Use

### Market Conditions
- **Ranging / Consolidating markets:** Mean-reversion trades bouncing between bands.
- **Pre-breakout setups:** Band squeeze (narrowing bands) signals an impending volatility expansion.
- **Trending markets:** Band walks (price hugging upper or lower band) confirm strong directional moves.
- **Volatility assessment:** Band width reveals whether the market is compressed or extended.

### Best Timeframes
| Timeframe | Use Case                                         |
|-----------|--------------------------------------------------|
| M5 / M15  | Scalping squeezes and band touches               |
| M30 / H1  | Intraday mean-reversion and breakout entries      |
| H4        | Swing trade setups, primary analysis timeframe    |
| D1        | Position trades, macro volatility context         |

### XAUUSD-Specific Considerations
- Gold is significantly more volatile than forex pairs; standard 2.0 deviation often gets
  pierced frequently, generating false signals.
- **Use deviation = 2.5** for XAUUSD to reduce false band touches. This creates wider bands
  that better capture gold's volatility range.
- During London/NY overlap (13:00-17:00 UTC), bands expand naturally due to session volatility.
  Do not interpret this expansion alone as a breakout signal.
- Gold trends can persist for days; band walks on H4/D1 are common during strong macro moves
  (Fed, NFP, CPI events).

---

## Parameters Guide

| Parameter | Default | Effect of Lower            | Effect of Higher            | XAUUSD Recommendation       |
|-----------|---------|----------------------------|-----------------------------|------------------------------|
| period    | 20      | More responsive bands, more noise, faster squeeze detection | Smoother bands, more lag, fewer false touches | 20 (standard) or 25 for D1 |
| deviation | 2.0     | Tighter bands, more frequent touches, more signals | Wider bands, fewer touches, higher-quality signals | **2.5** for XAUUSD on all TFs |

**Parameter tuning rationale for XAUUSD:**
- Gold's average daily range is 250-400 pips ($25-$40), compared to EURUSD at 60-80 pips.
  The 2.5 deviation compensates for this, keeping band touches meaningful.
- Period 20 works well across timeframes. Avoid going below 15 as gold's noise creates
  erratic bands. For D1 macro analysis, period 25 smooths nicely.

---

## Key Patterns & Setups

### Pattern 1: Band Squeeze Breakout (Low Volatility to Expansion)

**Description:** When Bollinger bandwidth narrows to a multi-period low, it signals compressed
volatility that typically resolves with an explosive breakout. The direction of the breakout
determines the trade. This is one of the highest-probability Bollinger setups.

**Identification:** Bandwidth drops below a threshold (e.g., 0.015 for XAUUSD H4). Then
price closes outside the band, confirming breakout direction.

**Playbook conditions (long breakout):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "(ind.h4_bollinger.upper - ind.h4_bollinger.lower) / ind.h4_bollinger.middle",
      "operator": "<",
      "right": "0.02",
      "description": "Bollinger bandwidth is squeezed (below 2%)"
    },
    {
      "left": "_price",
      "operator": ">",
      "right": "ind.h4_bollinger.upper",
      "description": "Price breaks above upper band (bullish breakout)"
    },
    {
      "left": "ind.h4_atr.value",
      "operator": ">",
      "right": "prev.h4_atr.value",
      "description": "ATR expanding confirms volatility breakout"
    }
  ]
}
```

**Playbook conditions (short breakout):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "(ind.h4_bollinger.upper - ind.h4_bollinger.lower) / ind.h4_bollinger.middle",
      "operator": "<",
      "right": "0.02",
      "description": "Bollinger bandwidth is squeezed"
    },
    {
      "left": "_price",
      "operator": "<",
      "right": "ind.h4_bollinger.lower",
      "description": "Price breaks below lower band (bearish breakout)"
    }
  ]
}
```

**Notes:**
- After a squeeze breakout, expect the initial move to reach at least 1x the prior
  bandwidth range in the breakout direction.
- False breakouts happen. Combine with volume or ATR expansion for confirmation.

---

### Pattern 2: Mean Reversion at Band Touch

**Description:** In ranging markets, price tends to revert to the middle band after touching
the upper or lower band. This is the classic Bollinger bounce strategy.

**Key requirement:** Market must be ranging (ADX < 25). In trending markets, band touches
are continuation signals, NOT reversal signals.

**Playbook conditions (long — bounce from lower band):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "_price",
      "operator": "<=",
      "right": "ind.h1_bollinger.lower",
      "description": "Price at or below lower Bollinger band"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": "<",
      "right": "25",
      "description": "ADX below 25 confirms ranging market (mean reversion valid)"
    },
    {
      "left": "ind.h1_rsi.value",
      "operator": "<",
      "right": "35",
      "description": "RSI confirms oversold condition"
    }
  ]
}
```

**Target:** Middle band (`ind.h1_bollinger.middle`).
**Stop loss:** Below the lower band by 1x ATR: `ind.h1_bollinger.lower - ind.h1_atr.value`

---

### Pattern 3: Band Walk (Trend Continuation)

**Description:** During strong trends, price "walks" along the upper band (uptrend) or lower
band (downtrend). Price repeatedly touches or pierces the band while staying above/below the
middle band. This signals trend strength, NOT reversal.

**Critical distinction from mean reversion:** If ADX > 25 and price is walking the band,
do NOT fade the move. Instead, trade pullbacks to the middle band as continuation entries.

**Playbook conditions (bullish band walk — buy pullback to middle):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "prev.h4_bollinger.upper",
      "operator": "<",
      "right": "_price",
      "description": "Previous bar was above upper band (band walk in progress)"
    },
    {
      "left": "_price",
      "operator": "<=",
      "right": "ind.h4_bollinger.middle",
      "description": "Price has pulled back to middle band"
    },
    {
      "left": "ind.h4_adx.adx",
      "operator": ">",
      "right": "30",
      "description": "ADX confirms strong trend"
    },
    {
      "left": "ind.h4_adx.plus_di",
      "operator": ">",
      "right": "ind.h4_adx.minus_di",
      "description": "+DI > -DI confirms bullish direction"
    }
  ]
}
```

**Notes:**
- In a band walk, the middle band acts as dynamic support (uptrend) or resistance (downtrend).
- If price closes below the middle band during an uptrend band walk, the trend may be weakening.

---

### Pattern 4: Double Bottom at Lower Band (W-Pattern)

**Description:** Price touches the lower band, bounces to the middle band, then retests the
lower band area but forms a higher low (second touch does not reach the band or barely touches
it). This W-pattern is a strong reversal signal, especially with RSI divergence.

**Playbook conditions (long):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "_price",
      "operator": "<=",
      "right": "ind.h4_bollinger.lower + ind.h4_atr.value * 0.3",
      "description": "Price near lower band (within 0.3 ATR)"
    },
    {
      "left": "_price",
      "operator": ">",
      "right": "ind.h4_bollinger.lower",
      "description": "Price above the lower band (higher low forming)"
    },
    {
      "left": "ind.h4_rsi.value",
      "operator": ">",
      "right": "prev.h4_rsi.value",
      "description": "RSI making higher low (bullish divergence hint)"
    }
  ]
}
```

---

### Pattern 5: Bandwidth Expansion Filter (Volatility Gate)

**Description:** Use bandwidth as a filter to avoid trading during dead markets. If bands are
extremely tight, neither mean-reversion nor trend strategies work well because there is no
movement to capture. Require minimum bandwidth before entering any trade.

**Playbook conditions (filter — add to any strategy):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "(ind.h4_bollinger.upper - ind.h4_bollinger.lower) / ind.h4_bollinger.middle",
      "operator": ">",
      "right": "0.008",
      "description": "Minimum bandwidth filter — avoid dead/illiquid markets"
    }
  ]
}
```

**XAUUSD bandwidth reference values (H4):**
| Bandwidth Value | Market State                  | Action           |
|-----------------|-------------------------------|------------------|
| < 0.008         | Dead market / pre-news        | Avoid trading    |
| 0.008 - 0.015   | Low volatility / squeeze      | Watch for breakout|
| 0.015 - 0.035   | Normal volatility             | Standard trading |
| 0.035 - 0.060   | High volatility               | Wider stops needed|
| > 0.060         | Extreme volatility (news)     | Reduce size or skip|

---

## Combinations

| Combo Indicator    | Purpose                      | Confluence Type     | Example                                    |
|--------------------|------------------------------|---------------------|--------------------------------------------|
| + ATR              | Volatility-adjusted stops    | SL/TP sizing        | SL at opposite band, confirmed by ATR      |
| + RSI              | Confirm overbought/oversold  | Entry confirmation  | Band touch + RSI extreme = stronger signal |
| + ADX              | Distinguish trend vs range   | Regime filter       | ADX < 25 = mean reversion, > 25 = trend    |
| + MACD             | Momentum confirmation        | Entry confirmation  | Band breakout + MACD crossover             |
| + EMA (50/200)     | Trend direction bias         | Directional filter  | Only buy at lower band if above EMA 200    |
| + Stochastic       | Timing within bands          | Entry timing        | Lower band + Stochastic %K < 20 + K cross D|
| + CCI              | Momentum at extremes         | Entry confirmation  | Band touch + CCI at -100/+100              |
| + SMC_Structure    | Institutional levels         | Zone confluence     | Band touch at order block = high-quality   |

**Best combination for XAUUSD:** Bollinger + ADX + ATR. ADX tells you whether to mean-revert
or trend-follow at the bands. ATR sizes your stops properly for gold's volatility.

---

## Position Management

### Dynamic Stop Loss — Opposite Band

Place SL at the opposite band. For a long trade entered at the lower band, SL trails below
the lower band. For a short trade entered at the upper band, SL trails above the upper band.

```json
{
  "stop_loss": {
    "type": "dynamic",
    "long_sl_expr": "ind.h4_bollinger.lower - ind.h4_atr.value * 0.5",
    "short_sl_expr": "ind.h4_bollinger.upper + ind.h4_atr.value * 0.5",
    "description": "SL at opposite band with 0.5 ATR buffer"
  }
}
```

### Dynamic Take Profit — Middle Band (Mean Reversion)

For mean-reversion trades, target the middle band as TP1 and the opposite band as TP2.

```json
{
  "take_profit": {
    "tp1_expr": "ind.h4_bollinger.middle",
    "tp1_portion": 0.5,
    "tp2_expr": "ind.h4_bollinger.upper",
    "tp2_portion": 0.5,
    "description": "TP1 at middle band (50%), TP2 at opposite band (50%)"
  }
}
```

### Trailing Stop — Middle Band as Trail

In trend trades (band walk), trail the stop to the middle band. As the trend progresses,
the middle band moves in the trend direction, locking in profits.

```json
{
  "trailing_stop": {
    "type": "indicator",
    "long_trail_expr": "ind.h4_bollinger.middle - ind.h4_atr.value * 0.3",
    "short_trail_expr": "ind.h4_bollinger.middle + ind.h4_atr.value * 0.3",
    "description": "Trail stop at middle Bollinger band with small ATR buffer"
  }
}
```

### Partial Close on Band Touch

When price reaches the opposite band, close 50-70% of the position and trail the remainder.
This captures the bulk of the mean-reversion move while allowing for extended runs.

---

## Pitfalls

1. **Treating every band touch as a reversal.** In trending markets, price walks the bands.
   Band touches during trends are continuation signals. Always check ADX or trend direction
   before fading a band touch. Rule: if ADX > 25, do NOT mean-revert at band touches.

2. **Using standard 2.0 deviation on XAUUSD.** Gold's volatility means price frequently
   pierces 2.0-deviation bands. Use 2.5 deviation for XAUUSD to get meaningful touches.
   With 2.0, you will get too many signals, most of them noise.

3. **Trading squeezes without direction confirmation.** A squeeze tells you volatility is
   coming, but NOT which direction. Wait for the actual breakout candle to close outside
   the band before entering. Do not anticipate the breakout direction.

4. **Ignoring the middle band.** The middle band (20-SMA) is the most important level. It
   acts as dynamic S/R. In uptrends, pullbacks to the middle band are buy opportunities.
   Many traders only watch upper/lower bands and miss the middle band's significance.

5. **Using Bollinger alone.** Bollinger Bands tell you about volatility and price position
   relative to its recent range. They do NOT tell you about momentum or trend strength.
   Always combine with at least one momentum indicator (RSI, CCI, MACD) and one trend
   filter (ADX, EMA).

6. **Confusing bandwidth contraction with directionlessness.** Low bandwidth means low
   volatility, not necessarily a ranging market. A trending market can have low bandwidth
   if the trend is orderly. Check ADX alongside bandwidth for accurate market regime
   classification.

7. **Over-optimizing deviation and period.** Resist the urge to curve-fit Bollinger
   parameters to historical data. The standard period=20, deviation=2.5 (for XAUUSD) works
   robustly across market conditions. Exotic parameter sets break in live trading.

---

## XAUUSD-Specific Notes

### Recommended Default Parameters
```
period = 20
deviation = 2.5
```

### Session-Based Behavior
| Session              | Bollinger Behavior                                  | Trading Approach          |
|----------------------|-----------------------------------------------------|---------------------------|
| Asian (00:00-07:00 UTC) | Bands contract, price stays near middle band       | Watch for squeeze setups  |
| London (07:00-12:00 UTC)| Bands start expanding, breakouts from Asian range  | Trade breakout direction  |
| NY (12:00-17:00 UTC)   | Maximum band width, strong directional moves       | Band walk / trend trades  |
| London Close (15:00-17:00)| Bands may begin contracting                      | Reduce new entries        |

### XAUUSD Bandwidth Thresholds (H4)
- **Squeeze threshold:** Bandwidth < 0.015 (extremely tight for gold)
- **Normal range:** 0.015 - 0.040
- **High volatility:** 0.040 - 0.060
- **News/event spike:** > 0.060 (widen stops or sit out)

### Gold-Specific Band Walk Characteristics
Gold trends more persistently than most forex pairs. When XAUUSD enters a band walk:
- It can walk the upper band for 5-15 H4 candles (1-4 days) without touching the middle band.
- Pullbacks to the middle band during gold band walks are shallow — typically 30-50% of the
  band width, not full retracements.
- Strong band walks on D1 can last weeks during macro trends (e.g., risk-off, dollar weakness).

### Combining with Gold-Specific Levels
- When a Bollinger band aligns with a round number (e.g., $2000, $2050, $2100), the level
  becomes significantly stronger as S/R.
- When a band touch occurs at an SMC order block or FVG, the confluence dramatically
  increases the probability of a reaction.

### ATR-Adjusted Band Interpretation
Because gold's ATR varies widely by session and day, consider using ATR to normalize your
interpretation of band touches:
- A band touch during low-ATR periods (Asian session) is weaker than during high-ATR
  periods (NY session).
- Distance from middle band in ATR units: `(_price - ind.h4_bollinger.middle) / ind.h4_atr.value`
  Values > 2.0 indicate extreme extension regardless of band position.
