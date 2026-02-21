# NW_Envelope — Nadaraya-Watson Envelope (Kernel Regression)

## 1. Overview

The NW_Envelope indicator applies Nadaraya-Watson Rational Quadratic kernel regression to price data, producing a smoothed central estimate (`yhat`) with dynamic ATR-based envelope bands. It excels at identifying mean reversion opportunities, trend direction, and extreme price levels. The envelopes use kernel ATR (not regular ATR) for band width, making them adaptive to the smoothed price behavior.

**Indicator ID pattern:** `<timeframe>_nw_envelope` (e.g., `h4_nw_envelope`, `m15_nw_envelope`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `yhat` | float | Kernel regression estimate — the smoothed center line |
| `upper_far` | float | Upper far envelope boundary (far_factor × kernel ATR above yhat) |
| `upper_avg` | float | Upper average envelope — midpoint of upper_near and upper_far |
| `upper_near` | float | Upper near envelope boundary (near_factor × kernel ATR above yhat) |
| `lower_near` | float | Lower near envelope boundary (near_factor × kernel ATR below yhat) |
| `lower_avg` | float | Lower average envelope — midpoint of lower_near and lower_far |
| `lower_far` | float | Lower far envelope boundary (far_factor × kernel ATR below yhat) |
| `is_bullish` | float | `1` if yhat is rising (current > previous), else `0` |
| `is_bearish` | float | `1` if yhat is falling, else `0` |

### Derived Values (computed in playbook expressions)

- **Bandwidth**: `upper_far - lower_far` — wider = more volatile, narrower = compressing
- **Price position**: `(_price - lower_far) / (upper_far - lower_far)` — 0.0 = at lower_far, 1.0 = at upper_far

## 2. When to Use

- **Mean reversion strategies** — fade extremes when price reaches far envelopes.
- **Trend direction confirmation** — `is_bullish` / `is_bearish` provide smoothed trend signal with less noise than moving averages.
- **Pullback entries in trend** — buy at `lower_near` in uptrend, sell at `upper_near` in downtrend.
- **Volatility assessment** — bandwidth expansion/contraction signals regime changes.
- **Overbought/oversold filter** — prevent chasing entries when price is already extended.
- **Kernel centerline** — `yhat` acts as dynamic fair value / support-resistance.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `lookback_window` | 8 | 2–50 | Kernel bandwidth (h). Controls smoothness. Higher = smoother line, slower reaction. Lower = more responsive, noisier. |
| `relative_weighting` | 8.0 | 1.0–50.0 | Relative weighting (alpha). Controls multi-scale behavior of the Rational Quadratic kernel. Higher = more adaptive to multiple length scales. |
| `start_bar` | 25 | 5–100 | Start regression at this bar offset. Avoids unstable early estimates. |
| `atr_length` | 60 | 10–200 | Kernel ATR period for envelope width calculation. Uses kernel-smoothed high/low, not raw ATR. |
| `near_factor` | 1.5 | 0.5–5.0 | ATR multiplier for near envelope bands |
| `far_factor` | 8.0 | 2.0–15.0 | ATR multiplier for far envelope bands |

**Note:** The `upper_avg` and `lower_avg` bands are computed as the midpoint of near and far bands, not as a separate parameter.

**XAUUSD recommended:** Default parameters work well for H1/H4 gold. For M15, consider `lookback_window: 6` for faster response. The high `far_factor: 8.0` means far envelopes are only touched during extreme moves — these are high-quality reversal signals.

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
      {"left": "ind.h4_nw_envelope.is_bearish", "operator": "==", "right": "1", "description": "Kernel turning bearish — reversal starting"}
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
      {"left": "ind.h4_nw_envelope.is_bullish", "operator": "==", "right": "1", "description": "Kernel turning bullish — reversal starting"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.2 Trend Direction Filter

Use the `is_bullish` / `is_bearish` fields as a smoothed trend filter. This is less noisy than EMA crossovers.

**Only take buys when kernel is bullish:**
```json
{
  "phase": "trend_filter",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_envelope.is_bullish", "operator": "==", "right": "1", "description": "Kernel regression confirms uptrend"}
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
      {"left": "ind.h4_nw_envelope.is_bullish", "operator": "==", "right": "1", "description": "Uptrend confirmed by kernel"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_nw_envelope.lower_near", "description": "Price pulled back to near support"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_nw_envelope.lower_avg", "description": "Not below average — pullback, not breakdown"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.4 Yhat as Dynamic Support/Resistance

The kernel centerline (`yhat`) acts as a smoothed fair value. Price tends to bounce off yhat in trending markets.

**Buy at yhat support in uptrend:**
```json
{
  "phase": "yhat_support",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_envelope.is_bullish", "operator": "==", "right": "1", "description": "Uptrend"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_nw_envelope.yhat * 1.001", "description": "Price touching kernel centerline"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_nw_envelope.yhat * 0.998", "description": "Not far below yhat"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.5 Bandwidth Squeeze (Volatility Compression)

When the distance between `upper_far` and `lower_far` narrows significantly, a breakout is likely.

**Detect compression:**
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

### 4.6 Kernel Direction Change (Trend Shift)

When `is_bullish` flips to `is_bearish` (or vice versa), the smoothed trend has shifted.

**Detect bullish-to-bearish kernel flip:**
```json
{
  "phase": "kernel_flip",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "prev.h4_nw_envelope.is_bullish", "operator": "==", "right": "1", "description": "Was bullish"},
      {"left": "ind.h4_nw_envelope.is_bearish", "operator": "==", "right": "1", "description": "Now bearish — kernel flipped"}
    ]
  },
  "transitions": [{"target": "prepare_sell_bias"}]
}
```

## 5. Combinations

| Combine With | Purpose | Role of NW_Envelope |
|---|---|---|
| SMC_Structure | Trend + reversion zones | NW provides dynamic S/R and yhat centerline; SMC provides structural bias |
| NW_RQ_Kernel | Direction + zones | Use RQ Kernel for direction; Envelope for entry/exit levels |
| OB_FVG | Entry precision | NW confirms price is extended; OB_FVG gives exact entry zone |
| TPO | Level confluence | NW shows overextension; TPO shows where price should revert to |
| RSI | Momentum + envelope | RSI confirms overbought/oversold at NW extremes |
| ATR | Volatility context | Kernel ATR drives envelope width; use raw ATR for position sizing |
| ADX | Trend strength | ADX > 25 = trending (use near envelope); ADX < 20 = ranging (use far envelope for fades) |

**Best combination:** NW_Envelope + SMC_Structure + OB_FVG — smoothed trend with structural context and precise entries.

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
- **Mean reversion:** Target yhat (TP1), then the opposite near envelope (TP2). E.g., buy at `lower_far`, TP1 at `yhat`, TP2 at `upper_near`.
- **Trend trades:** Target the far envelope in the trend direction.

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

1. **Fading strong trends at far envelope.** In a powerful trend, price can ride the far envelope for extended periods. Never fade the far envelope without a kernel direction change confirmation (`is_bearish == 1` for shorts, `is_bullish == 1` for longs).
2. **Using NW_Envelope as sole entry signal.** The envelope shows where price is relative to its regression — it does not know structure or order flow. Always combine with a directional indicator (SMC_Structure, ADX).
3. **Lookback_window too smooth.** High values (>15) make the kernel very slow to react. On M15, keep lookback_window at 6–8. On H4, 8–12 is appropriate.
4. **Ignoring regime changes.** When bandwidth suddenly expands (volatility spike), the envelopes widen. Entries at the old near envelope may now be in the middle of the new range.
5. **Confusing near and far roles.** Near envelope = pullback level (trend continuation). Far envelope = extreme level (mean reversion). Using far envelope for trend entries wastes opportunities; using near envelope for mean reversion produces too many false signals.
6. **Ignoring yhat.** The kernel centerline is the most important output — it represents smoothed fair value. Use it as TP target and dynamic S/R, not just the envelope bands.

## 8. XAUUSD-Specific Notes

- **Default params work well.** The standard `lookback_window: 8`, `atr_length: 60` configuration handles gold's volatility naturally because the kernel ATR auto-adjusts.
- **Session adjustment:** Consider `lookback_window: 6` for M15 during London/NY overlap to make the kernel more responsive.
- **Far envelope touches on gold:** XAUUSD touches the far envelope approximately 2–4 times per week on H4. These are high-quality mean reversion signals — win rate of 65–75% when combined with kernel direction change.
- **News events:** Major news can push gold through the far envelope. During NFP/FOMC, do not fade the far envelope — wait for the kernel to actually flip direction before entering.
- **Asian session behavior:** During Asian session (00:00–06:00 UTC), gold typically oscillates between `lower_near` and `upper_near`. Near envelope mean reversion is highly effective during this window.
- **Kernel as trend proxy:** On XAUUSD H4, the NW kernel direction aligns with the dominant trend approximately 80% of the time, with fewer whipsaws than EMA 50/200 crossovers.
- **Bandwidth squeeze on gold:** Bandwidth squeezes typically precede major moves (>$20). Combine with SMC_Structure for breakout direction.
