# ATR (Average True Range) — Playbook Skills

## Overview

The Average True Range (ATR) measures market volatility by calculating the average of the
true range over N periods. The true range is the greatest of: (1) current high minus current
low, (2) absolute value of current high minus previous close, (3) absolute value of current
low minus previous close. ATR does not indicate direction — it measures how much price moves
regardless of direction.

ATR is the foundational indicator for position sizing, stop-loss placement, take-profit
targets, and volatility filtering. It translates subjective "volatility" into a concrete
number in price units (dollars for XAUUSD).

**Indicator ID format:** `ind.<tf>_atr` (e.g., `ind.h4_atr`, `ind.h1_atr`, `ind.d1_atr`)

**Outputs:**
| Field | Access Expression       | Description                              |
|-------|-------------------------|------------------------------------------|
| value | `ind.h4_atr.value`      | ATR value in price units (e.g., $12.50)  |

**Previous bar access:** `prev.h4_atr.value` — ATR from the prior completed bar.

---

## When to Use

### Market Conditions
- **Always.** ATR should be included in virtually every playbook as a sizing and filtering
  component. It is not a standalone entry signal but a critical risk management tool.
- **Volatility filtering:** Reject entries when ATR is too low (dead market, no opportunity)
  or too high (chaotic, whipsaw risk).
- **Position sizing:** Scale lot size inversely with ATR to maintain constant dollar risk.
- **SL/TP calibration:** Set stops and targets as multiples of ATR for volatility-adaptive
  risk management.

### Best Timeframes
| Timeframe | ATR Use Case                                              |
|-----------|-----------------------------------------------------------|
| M5 / M15  | Scalping SL/TP sizing, micro-volatility filter            |
| M30 / H1  | Intraday trade management, session volatility detection   |
| H4        | **Primary SL/TP sizing timeframe**, swing trade management|
| D1        | Macro volatility context, position trade sizing           |

### XAUUSD-Specific Considerations
- XAUUSD ATR is expressed in dollars per ounce (e.g., ATR = 15.0 means $15 average range).
- Gold's ATR varies dramatically by session and by day of week.
- Always check ATR on the timeframe matching your trade's intended holding period.
- ATR can spike 2-3x during news events (NFP, FOMC, CPI) — these spikes are temporary
  and should not be used for normal SL/TP sizing.

---

## Parameters Guide

| Parameter | Default | Effect of Lower               | Effect of Higher              | XAUUSD Recommendation       |
|-----------|---------|-------------------------------|-------------------------------|-----------------------------|
| period    | 14      | More responsive to recent volatility spikes, noisier | Smoother, lags behind volatility changes | 14 (standard) for all TFs |

**Why 14 works for XAUUSD:** The default period of 14 provides a good balance between
responsiveness and smoothness. On H4, 14 periods covers 2.3 trading days, which is enough
to capture the current volatility regime without overreacting to single-bar spikes. On D1,
14 periods covers about 3 weeks of data.

**Alternative periods:**
- Period 7: Use for very short-term scalping where you need ATR to react within hours.
- Period 20: Use for position trades or D1 analysis where you want a more stable reading.
- Avoid period < 5 as ATR becomes too noisy for reliable SL/TP calculations.

---

## Key Patterns & Setups

### Pattern 1: ATR-Based Stop Loss and Take Profit (Foundation)

**Description:** The most common ATR usage. Set SL at 1.5x ATR below entry (long) or above
entry (short). Set TP at 2-3x ATR for a favorable risk/reward ratio. This creates
volatility-adaptive exits that are wider in volatile markets and tighter in quiet markets.

**Playbook SL/TP sizing:**
```json
{
  "stop_loss": {
    "type": "atr_multiple",
    "long_sl_expr": "_price - ind.h4_atr.value * 1.5",
    "short_sl_expr": "_price + ind.h4_atr.value * 1.5",
    "description": "SL at 1.5x ATR from entry"
  },
  "take_profit": {
    "tp1_expr_long": "_price + ind.h4_atr.value * 2.0",
    "tp1_expr_short": "_price - ind.h4_atr.value * 2.0",
    "tp1_portion": 0.5,
    "tp2_expr_long": "_price + ind.h4_atr.value * 3.0",
    "tp2_expr_short": "_price - ind.h4_atr.value * 3.0",
    "tp2_portion": 0.5,
    "description": "TP1 at 2x ATR (50%), TP2 at 3x ATR (50%) — 1:1.33 to 1:2 R:R"
  }
}
```

**XAUUSD SL/TP multiplier guide:**
| Strategy Style | SL Multiplier | TP Multiplier | Effective R:R |
|----------------|---------------|---------------|---------------|
| Scalping       | 1.0x ATR      | 1.5x ATR      | 1:1.5         |
| Intraday       | 1.5x ATR      | 2.0-3.0x ATR  | 1:1.3 - 1:2   |
| Swing          | 2.0x ATR      | 3.0-4.0x ATR  | 1:1.5 - 1:2   |
| Position       | 2.5x ATR      | 4.0-6.0x ATR  | 1:1.6 - 1:2.4 |

---

### Pattern 2: Volatility Filter — Minimum ATR for Entry

**Description:** Reject trades when ATR is below a minimum threshold. Low ATR means the
market is not moving enough to overcome spread and commission costs, and breakouts in
low-ATR environments frequently fail.

**Playbook conditions (filter — add to any strategy):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_atr.value",
      "operator": ">",
      "right": "5.0",
      "description": "H4 ATR above $5 — minimum volatility for XAUUSD entry"
    }
  ]
}
```

**XAUUSD ATR minimum thresholds by timeframe:**
| Timeframe | Minimum ATR (Avoid Below) | Normal Range    | High (Caution)  |
|-----------|---------------------------|-----------------|-----------------|
| M5        | $1.50                     | $2.00 - $5.00   | > $8.00         |
| M15       | $2.50                     | $3.00 - $8.00   | > $12.00        |
| H1        | $4.00                     | $5.00 - $15.00  | > $20.00        |
| H4        | $5.00                     | $8.00 - $25.00  | > $35.00        |
| D1        | $15.00                    | $20.00 - $45.00 | > $60.00        |

---

### Pattern 3: Volatility Filter — Maximum ATR (Chaos Filter)

**Description:** Reject trades when ATR is above a maximum threshold. Extremely high ATR
indicates news-driven chaos, flash crashes, or illiquid spikes. During these conditions,
slippage is high, whipsaws are common, and even good setups fail.

**Playbook conditions (filter):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_atr.value",
      "operator": "<",
      "right": "40.0",
      "description": "H4 ATR below $40 — avoid chaotic/news-driven markets"
    }
  ]
}
```

**Combined min/max ATR filter (recommended for all XAUUSD playbooks):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_atr.value",
      "operator": ">",
      "right": "5.0",
      "description": "Minimum volatility — market is moving enough"
    },
    {
      "left": "ind.h4_atr.value",
      "operator": "<",
      "right": "40.0",
      "description": "Maximum volatility — market is not chaotic"
    }
  ]
}
```

---

### Pattern 4: ATR Expansion — Breakout Confirmation

**Description:** When ATR is rising (current ATR > previous ATR), it confirms that a breakout
or trend move has genuine momentum. Breakouts on declining ATR often fail. Use ATR expansion
as a confirmation filter for breakout strategies.

**Playbook conditions (breakout confirmation):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_atr.value",
      "operator": ">",
      "right": "prev.h4_atr.value * 1.1",
      "description": "ATR expanding by at least 10% — breakout is genuine"
    },
    {
      "left": "ind.h4_atr.value",
      "operator": ">",
      "right": "prev.h4_atr.value",
      "description": "ATR rising (simpler version)"
    }
  ]
}
```

**Notes:** For XAUUSD, a 10-15% ATR expansion within 2-3 bars is a meaningful signal. Larger
expansions (>30%) typically occur during news events and may indicate the move is already
extended.

---

### Pattern 5: ATR Contraction — Pre-Breakout Detection

**Description:** Declining ATR (volatility compression) often precedes a breakout. When ATR
drops to unusually low levels, the market is coiling for a move. Combine with Bollinger
squeeze or price range analysis for complete pre-breakout detection.

**Playbook conditions (volatility compression):**
```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_atr.value",
      "operator": "<",
      "right": "prev.h4_atr.value * 0.85",
      "description": "ATR contracting by 15%+ — volatility squeeze in progress"
    },
    {
      "left": "ind.h4_atr.value",
      "operator": "<",
      "right": "8.0",
      "description": "ATR below $8 on H4 — historically low for XAUUSD"
    }
  ]
}
```

**Usage:** Do not trade the compression itself. Instead, use this as a setup detector. When
compression is detected, switch to a breakout strategy and wait for the expansion move.

---

## Combinations

| Combo Indicator      | Purpose                          | Confluence Type     | Example                                   |
|----------------------|----------------------------------|---------------------|-------------------------------------------|
| + Bollinger Bands    | Squeeze detection, band width    | Volatility regime   | Low ATR + tight bands = imminent breakout |
| + ADX                | Trend + volatility dual filter   | Regime classification| ADX > 25 + rising ATR = trending market  |
| + RSI / CCI          | Momentum with proper SL sizing  | SL/TP calibration   | RSI signal, ATR-sized stop               |
| + EMA                | Trend direction + sizing         | Directional + sizing| Trade EMA direction, size by ATR         |
| + SMC_Structure      | Smart money + volatility         | Entry + sizing      | OB entry, ATR-based SL                   |
| + MACD               | Momentum confirmation + sizing   | Entry + sizing      | MACD cross + ATR SL/TP                   |
| + Stochastic         | Mean-reversion + sizing          | Entry + sizing      | Stoch oversold + ATR-based TP            |

**ATR should be combined with EVERY indicator.** It is the universal sizing companion. No
playbook should calculate SL/TP without referencing ATR.

---

## Position Management

### Chandelier Trailing Stop

The Chandelier Exit trails the stop at N * ATR below the highest high (for longs) or above
the lowest low (for shorts) since entry. This is one of the most robust trailing methods.

```json
{
  "trailing_stop": {
    "type": "chandelier",
    "long_trail_expr": "_price - ind.h4_atr.value * 2.0",
    "short_trail_expr": "_price + ind.h4_atr.value * 2.0",
    "description": "Chandelier trailing stop at 2x ATR from price"
  }
}
```

**Chandelier multiplier guide for XAUUSD:**
| Trade Style | ATR Multiplier | Behavior                                   |
|-------------|----------------|---------------------------------------------|
| Tight       | 1.5x           | Locks profits quickly, gets stopped often    |
| Standard    | 2.0x           | Balanced — good for most XAUUSD strategies   |
| Wide        | 3.0x           | Rides big trends, gives back more on reversals|

### ATR-Based Position Sizing

Scale position size inversely with ATR to maintain constant dollar risk per trade:

```
Position Size = (Account Risk $) / (ATR * SL Multiplier * Pip Value)
```

Example for XAUUSD:
- Account risk: $100 per trade
- H4 ATR: $15.00
- SL multiplier: 1.5x
- SL distance: $15.00 * 1.5 = $22.50
- Lot size: $100 / ($22.50 * $1/pip for 0.01 lot) = adjusted accordingly

This ensures that a trade during a $25 ATR period uses smaller size than a $10 ATR period,
keeping risk constant.

### Partial Close at ATR Targets

```json
{
  "take_profit": {
    "tp1_expr_long": "_price + ind.h4_atr.value * 1.5",
    "tp1_portion": 0.33,
    "tp2_expr_long": "_price + ind.h4_atr.value * 2.5",
    "tp2_portion": 0.33,
    "tp3_expr_long": "_price + ind.h4_atr.value * 4.0",
    "tp3_portion": 0.34,
    "description": "Three-tier ATR-based TP: 1.5x (33%), 2.5x (33%), 4x (34%)"
  }
}
```

### Break-Even Move

Move SL to break-even when price has moved 1x ATR in your favor:

```json
{
  "break_even": {
    "trigger_distance": "ind.h4_atr.value * 1.0",
    "description": "Move SL to entry when price moves 1x ATR in profit"
  }
}
```

---

## Pitfalls

1. **Using fixed-pip stops on XAUUSD.** A $10 stop makes sense when ATR is $15 but is
   suicidal when ATR is $35. Always use ATR-based stops. If you see a playbook with a
   fixed dollar stop, flag it as fragile.

2. **Ignoring ATR timeframe mismatch.** Using M5 ATR for an H4 trade results in a tiny
   stop that gets hit constantly. Match ATR timeframe to your trade's holding period.
   Rule: SL/TP should use ATR from the entry signal's timeframe.

3. **Trading during ATR spikes (news events).** A sudden ATR spike of 50%+ in a single bar
   means news hit. The ATR reading is temporarily inflated. Using the spiked ATR for SL/TP
   creates overly wide stops. Either wait 2-3 bars for ATR to normalize or use the
   pre-spike ATR value.

4. **Confusing ATR with direction.** ATR tells you how much price moves, not which direction.
   Rising ATR does not mean price is going up — it means price is moving more. Always pair
   ATR with a directional indicator.

5. **Setting SL too tight relative to ATR.** If your SL is less than 1x ATR, you will get
   stopped out by normal market noise. Minimum SL for XAUUSD: 1.0x ATR for scalps, 1.5x
   ATR for intraday, 2.0x ATR for swings.

6. **Not adjusting for session.** XAUUSD ATR during Asian session may be $5 on H1, but
   during NY session it could be $12. A playbook built on Asian ATR will have inadequate
   stops during NY. Consider using H4 ATR as it smooths session differences.

7. **Over-reliance on ATR expansion for breakout confirmation.** ATR is a lagging measure of
   volatility. By the time ATR expands meaningfully, the breakout may already be 60-70%
   complete. Use ATR expansion as confirmation, not as the primary entry trigger.

---

## XAUUSD-Specific Notes

### XAUUSD ATR Ranges by Timeframe and Session

| Timeframe | Asian Session | London Session | NY Session | Full Day Avg |
|-----------|---------------|----------------|------------|--------------|
| M5        | $1.50 - $3.00 | $2.50 - $5.00 | $3.00 - $7.00 | $2.00 - $5.00 |
| M15       | $2.50 - $5.00 | $4.00 - $8.00 | $5.00 - $12.00| $3.50 - $8.00 |
| H1        | $4.00 - $8.00 | $6.00 - $14.00| $8.00 - $20.00| $5.00 - $15.00|
| H4        | N/A (multi-session) | N/A      | N/A        | $8.00 - $25.00|
| D1        | N/A           | N/A            | N/A        | $20.00 - $45.00|

*Note: Ranges are approximate and vary with macro conditions. During high-volatility regimes
(e.g., rate hike cycles, geopolitical events), multiply the upper end by 1.5-2x.*

### ATR Normalization for Cross-Timeframe Analysis

When comparing ATR across timeframes, normalize by the square root of the time ratio:
- Expected H1 ATR from H4 ATR: `H4_ATR / sqrt(4)` = `H4_ATR / 2`
- Expected D1 ATR from H4 ATR: `H4_ATR * sqrt(6)` = `H4_ATR * 2.45`

This helps detect when a lower timeframe's ATR is abnormally high or low compared to the
higher timeframe, which signals unusual intra-bar volatility (potential news or liquidity event).

### Day-of-Week ATR Patterns for XAUUSD

| Day       | Typical ATR Behavior                                  |
|-----------|-------------------------------------------------------|
| Monday    | Below average — Asian open, low liquidity             |
| Tuesday   | Average to above — markets get active                 |
| Wednesday | Above average — mid-week positioning, often FOMC days |
| Thursday  | Highest average — NFP week Thursdays are big          |
| Friday    | Variable — high before NFP/data, low on quiet weeks   |

### Gold News Event ATR Impact

| Event    | Typical H1 ATR Spike | Duration  | Recommendation                   |
|----------|----------------------|-----------|----------------------------------|
| FOMC     | 2-3x normal          | 2-4 hours | Avoid 30 min before/after        |
| NFP      | 2-4x normal          | 1-3 hours | Avoid 15 min before, 60 after    |
| CPI      | 1.5-3x normal        | 1-2 hours | Avoid 15 min before, 45 after    |
| PPI      | 1.5-2x normal        | 1 hour    | Manageable with wider stops      |
| Geopolitical| 3-5x normal       | Hours-days| Reduce size, widen stops 2x      |

### Universal ATR Filter Template for XAUUSD

Add this to every XAUUSD playbook as a baseline volatility gate:

```json
{
  "type": "AND",
  "rules": [
    {
      "left": "ind.h4_atr.value",
      "operator": ">",
      "right": "5.0",
      "description": "ATR floor — market has enough movement for profitable trades"
    },
    {
      "left": "ind.h4_atr.value",
      "operator": "<",
      "right": "40.0",
      "description": "ATR ceiling — market is not in news-driven chaos"
    }
  ]
}
```
