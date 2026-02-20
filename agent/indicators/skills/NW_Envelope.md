# NW_Envelope — Nadaraya-Watson Envelope (Kernel Regression)

## 1. Overview

The NW_Envelope indicator applies Nadaraya-Watson kernel regression to price data, producing a smoothed central estimate with dynamic envelope bands. It excels at identifying mean reversion opportunities, trend direction, and extreme price levels. The envelope adapts to volatility, making it ideal for instruments like XAUUSD that shift between calm and volatile regimes.

**Indicator ID pattern:** `<timeframe>_nw_envelope` (e.g., `h4_nw_envelope`, `m15_nw_envelope`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `nw_bullish` | int | `1` if the kernel regression line is sloping upward (current > previous), else `0` |
| `nw_bearish` | int | `1` if the kernel regression line is sloping downward, else `0` |
| `upper_far` | float | Upper far envelope — extreme overbought level (typically 2.5-3x ATR above kernel) |
| `upper_avg` | float | Upper average envelope — moderate overbought (typically 1.5-2x ATR) |
| `upper_near` | float | Upper near envelope — mild overbought / first resistance (typically 0.5-1x ATR) |
| `lower_near` | float | Lower near envelope — mild oversold / first support |
| `lower_avg` | float | Lower average envelope — moderate oversold |
| `lower_far` | float | Lower far envelope — extreme oversold level |

### Derived Values (computed in playbook expressions)

- **Kernel midline** (approximate): `(upper_near + lower_near) / 2`
- **Bandwidth**: `upper_far - lower_far` — wider = more volatile, narrower = compressing
- **Price position**: `(_price - lower_far) / (upper_far - lower_far)` — 0.0 = at lower_far, 1.0 = at upper_far

## 2. When to Use

- **Mean reversion strategies** — fade extremes when price reaches far envelopes.
- **Trend direction confirmation** — `nw_bullish` / `nw_bearish` provide smoothed trend signal with less noise than moving averages.
- **Pullback entries in trend** — buy at `lower_near` in uptrend, sell at `upper_near` in downtrend.
- **Volatility assessment** — bandwidth expansion/contraction signals regime changes.
- **Overbought/oversold filter** — prevent chasing entries when price is already extended.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `bandwidth` | 8.0 | 2.0–40.0 | Kernel bandwidth (smoothing factor). Higher = smoother line, slower reaction. Lower = more responsive, noisier. |
| `lookback` | 200 | 50–500 | Number of bars used for kernel regression calculation |
| `atr_length` | 14 | 7–50 | ATR period for envelope width calculation |
| `near_mult` | 1.0 | 0.3–2.0 | ATR multiplier for near envelopes |
| `avg_mult` | 1.8 | 1.0–3.0 | ATR multiplier for average envelopes |
| `far_mult` | 2.7 | 2.0–5.0 | ATR multiplier for far envelopes |

**XAUUSD recommended:** Default parameters work well for H4 gold. For M15, consider `bandwidth: 6.0` for faster response. During high-volatility sessions (London/NY overlap), the far envelopes naturally widen via ATR — no manual adjustment needed.

## 4. Key Patterns & Setups

### 4.1 Mean Reversion at Far Envelope

Price reaching `upper_far` or `lower_far` indicates an extreme. These levels are touched rarely and tend to produce strong reversions.

**Sell at upper far envelope (extreme overbought):**
```json
{
  "phase": "extreme_sell",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">=", "right": "ind.h4_nw_envelope.upper_far", "description": "Price at upper far envelope — extreme overbought"},
      {"left": "ind.h4_nw_envelope.nw_bearish", "operator": "==", "right": "1", "description": "Kernel turning bearish — reversal starting"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

**Buy at lower far envelope (extreme oversold):**
```json
{
  "phase": "extreme_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": "<=", "right": "ind.h4_nw_envelope.lower_far", "description": "Price at lower far envelope — extreme oversold"},
      {"left": "ind.h4_nw_envelope.nw_bullish", "operator": "==", "right": "1", "description": "Kernel turning bullish — reversal starting"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.2 Trend Direction Filter

Use the `nw_bullish` / `nw_bearish` fields as a smoothed trend filter. This is less noisy than EMA crossovers.

**Only take buys when kernel is bullish:**
```json
{
  "phase": "trend_filter",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_envelope.nw_bullish", "operator": "==", "right": "1", "description": "Kernel regression confirms uptrend"}
    ]
  }
}
```

### 4.3 Pullback to Near Envelope in Trend

In an uptrend, price pulling back to `lower_near` is a high-probability entry. The near envelope acts as dynamic support/resistance.

**Buy at lower near during uptrend:**
```json
{
  "phase": "pullback_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_envelope.nw_bullish", "operator": "==", "right": "1", "description": "Uptrend confirmed by kernel"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_nw_envelope.lower_near", "description": "Price pulled back to near support"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_nw_envelope.lower_avg", "description": "Not below average — pullback, not breakdown"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Sell at upper near during downtrend:**
```json
{
  "phase": "pullback_sell",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_envelope.nw_bearish", "operator": "==", "right": "1", "description": "Downtrend confirmed"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_nw_envelope.upper_near", "description": "Price rallied to near resistance"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_nw_envelope.upper_avg", "description": "Not above average — rally, not breakout"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

### 4.4 Bandwidth Squeeze (Volatility Compression)

When the distance between `upper_far` and `lower_far` narrows significantly, a breakout is likely. Use a variable to track bandwidth.

**Detect compression and prepare for breakout:**
```json
{
  "phase": "detect_squeeze",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_envelope.upper_far - ind.h4_nw_envelope.lower_far", "operator": "<", "right": "var.avg_bandwidth * 0.6", "description": "Bandwidth compressed to <60% of average — squeeze detected"}
    ]
  },
  "transitions": [{"target": "wait_for_breakout"}]
}
```

### 4.5 Kernel Direction Change (Trend Shift)

When `nw_bullish` flips to `nw_bearish` (or vice versa), the smoothed trend has shifted. This is more reliable than raw price crossovers.

**Detect bullish-to-bearish kernel flip:**
```json
{
  "phase": "kernel_flip",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "prev.h4_nw_envelope.nw_bullish", "operator": "==", "right": "1", "description": "Was bullish"},
      {"left": "ind.h4_nw_envelope.nw_bearish", "operator": "==", "right": "1", "description": "Now bearish — kernel flipped"}
    ]
  },
  "transitions": [{"target": "prepare_sell_bias"}]
}
```

## 5. Combinations

| Combine With | Purpose | Role of NW_Envelope |
|---|---|---|
| SMC_Structure | Trend + reversion zones | NW provides dynamic S/R; SMC provides structural bias |
| Bollinger Bands | Double mean reversion | NW far envelope + Bollinger outer band = extreme reversal signal |
| RSI | Momentum + envelope | RSI confirms overbought/oversold at NW extremes |
| OB_FVG | Entry precision | NW confirms price is extended; OB_FVG gives exact entry zone |
| ATR | Volatility context | ATR drives envelope width; use raw ATR for position sizing |
| ADX | Trend strength | ADX > 25 = trending (use near envelope); ADX < 20 = ranging (use far envelope for fades) |

**Best combination:** NW_Envelope + RSI + SMC_Structure — smoothed trend with momentum confirmation and structural context.

## 6. Position Management

### Stop Loss
- **Mean reversion trades:** SL beyond the next envelope level. If entering at `lower_avg`, SL below `lower_far`.
- **Trend pullback trades:** SL below the `lower_avg` envelope (for buys).

```json
{
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_nw_envelope.lower_far",
    "offset": "-1.5",
    "description": "SL below lower far envelope with $1.50 buffer"
  }
}
```

### Take Profit
- **Mean reversion:** Target the opposite near envelope. E.g., buy at `lower_far`, TP at `upper_near`.
- **Trend trades:** Target the far envelope in the trend direction. E.g., buy pullback, TP at `upper_avg` or `upper_far`.

### Trailing
- Trail using the near envelope as dynamic stop. As the kernel line moves, the envelopes follow.

```json
{
  "trailing_stop": {
    "type": "indicator",
    "reference": "ind.h4_nw_envelope.lower_near",
    "description": "Trail stop at lower near envelope — moves with the kernel"
  }
}
```

## 7. Pitfalls

1. **Fading strong trends at far envelope.** In a powerful trend, price can ride the far envelope for extended periods. Never fade the far envelope without a kernel direction change confirmation (`nw_bearish == 1` for shorts, `nw_bullish == 1` for longs).
2. **Using NW_Envelope as sole entry signal.** The envelope shows where price is relative to its regression — it does not know structure or order flow. Always combine with a directional indicator (SMC_Structure, EMA, ADX).
3. **Bandwidth parameter too smooth.** High `bandwidth` values (>15) make the kernel very slow to react. On M15, keep bandwidth at 6-8. On H4, 8-12 is appropriate.
4. **Ignoring regime changes.** When bandwidth suddenly expands (volatility spike), the envelopes widen. Entries at the old near envelope may now be in the middle of the new range. Re-assess after volatility events.
5. **Overfitting envelope multipliers.** Resist the urge to optimize `near_mult`, `avg_mult`, `far_mult` on historical data. The defaults are designed for general use. Only adjust `atr_length` for different instruments.
6. **Confusing near and far roles.** Near envelope = pullback level (trend continuation). Far envelope = extreme level (mean reversion). Using far envelope for trend entries wastes opportunities; using near envelope for mean reversion produces too many false signals.

## 8. XAUUSD-Specific Notes

- **Default params work well.** The standard `bandwidth: 8.0`, `atr_length: 14` configuration handles gold's volatility naturally because the ATR-based envelopes auto-adjust.
- **Session adjustment:** Consider `atr_length: 10` for M15 during London/NY overlap to make envelopes more responsive to the higher intraday volatility.
- **Far envelope touches on gold:** XAUUSD touches the far envelope approximately 2-4 times per week on H4. These are high-quality mean reversion signals — win rate of 65-75% when combined with kernel direction change.
- **News events:** Major news can push gold through the far envelope and keep it there. During NFP/FOMC, do not fade the far envelope — wait for the kernel to actually flip direction before entering.
- **Asian session behavior:** During Asian session (00:00-06:00 UTC), gold typically oscillates between `lower_near` and `upper_near`. The near envelope mean reversion is highly effective during this low-volatility window.
- **Kernel as trend proxy:** On XAUUSD H4, the NW kernel direction aligns with the dominant trend approximately 80% of the time. It is a reliable alternative to EMA 50/200 crossovers, with fewer whipsaws.
- **Bandwidth squeeze on gold:** Gold bandwidth squeezes typically precede major moves (>$20). When bandwidth drops below 60% of its 20-bar average, expect a breakout within 4-8 H4 bars. Combine with SMC_Structure for breakout direction.
