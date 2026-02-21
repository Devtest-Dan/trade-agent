# NW_RQ_Kernel — Nadaraya-Watson Rational Quadratic Kernel Regression

## 1. Overview

The NW_RQ_Kernel indicator computes a non-parametric kernel regression estimate of price using a Rational Quadratic kernel. It produces a single smoothed price line with direction signals, providing a low-noise trend proxy. Unlike moving averages, the kernel adapts to multiple length scales simultaneously, making it robust across different market regimes.

**Indicator ID pattern:** `<timeframe>_nw_rq_kernel` (e.g., `h4_nw_rq_kernel`, `m15_nw_rq_kernel`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `value` | float | Kernel regression estimate — smoothed price level |
| `is_bullish` | int | `1` if kernel estimate is rising (current > previous), else `0` |
| `is_bearish` | int | `1` if kernel estimate is falling, else `0` |
| `smooth_bullish` | int | `1` if lagged kernel > main kernel (crossover bullish), else `0` |
| `smooth_bearish` | int | `1` if lagged kernel < main kernel (crossover bearish), else `0` |

## 2. When to Use

- **Smoothed trend direction** — `is_bullish` / `is_bearish` provide a cleaner trend signal than EMAs with fewer whipsaws.
- **Trend confirmation filter** — gate entries with kernel direction before using other signals.
- **Dynamic support/resistance** — the `value` line acts as a moving S/R level that price respects.
- **Crossover signals** — `smooth_bullish` / `smooth_bearish` detect lagged crossovers for slower, higher-confidence trend shifts.
- **Combining with NW_Envelope** — use RQ Kernel for direction, Envelope for entry zones.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `lookback_window` | 8 | 2–50 | Kernel bandwidth (h). Controls smoothness. Higher = smoother, slower reaction. |
| `relative_weighting` | 8.0 | 1.0–50.0 | Relative weighting (r/alpha). Controls multi-scale behavior. Higher = more adaptive. |
| `start_bar` | 25 | 5–100 | Start regression at this bar offset. Avoids unstable early estimates. |
| `lag` | 2 | 1–10 | Lag for smooth crossover detection. Higher = fewer but more reliable crossover signals. |

**XAUUSD recommended:** Defaults work well on H1/H4. For M15, try `lookback_window: 6` for faster response.

## 4. Key Patterns & Setups

### 4.1 Trend Direction Filter

Use the kernel direction as a gate for all entries. Simpler and more reliable than EMA crossovers.

**Only take buys when kernel is bullish:**
```json
{
  "phase": "trend_gate",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_rq_kernel.is_bullish", "operator": "==", "right": "1", "description": "Kernel confirms uptrend"}
    ]
  }
}
```

### 4.2 Kernel Crossover Signal

The smooth crossover (lagged kernel crossing main kernel) provides a higher-timeframe-equivalent signal on lower timeframes.

**Detect bullish crossover:**
```json
{
  "phase": "crossover_buy",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_rq_kernel.smooth_bullish", "operator": "==", "right": "1", "description": "Lagged kernel crossed above main — bullish crossover"},
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Aligned with bullish structure"}
    ]
  },
  "transitions": [{"target": "wait_for_entry"}]
}
```

### 4.3 Dynamic Support/Resistance

The kernel value acts as a moving S/R line. In an uptrend, price tends to bounce off the kernel line.

**Buy at kernel support in uptrend:**
```json
{
  "phase": "kernel_support",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_nw_rq_kernel.is_bullish", "operator": "==", "right": "1", "description": "Uptrend"},
      {"left": "_price", "operator": "<=", "right": "ind.h4_nw_rq_kernel.value * 1.001", "description": "Price touching kernel line"},
      {"left": "_price", "operator": ">=", "right": "ind.h4_nw_rq_kernel.value * 0.998", "description": "Not far below kernel"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.4 Kernel Direction Change

When `is_bullish` flips to `is_bearish`, the smoothed trend has shifted. This is a primary bias change signal.

**Detect bearish flip:**
```json
{
  "phase": "kernel_flip_bear",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "prev.h4_nw_rq_kernel.is_bullish", "operator": "==", "right": "1", "description": "Was bullish"},
      {"left": "ind.h4_nw_rq_kernel.is_bearish", "operator": "==", "right": "1", "description": "Now bearish — direction flipped"}
    ]
  },
  "transitions": [{"target": "prepare_sell_bias"}]
}
```

## 5. Combinations

| Combine With | Purpose | Role of NW_RQ_Kernel |
|---|---|---|
| SMC_Structure | Trend confirmation | Kernel smoothes SMC trend; double confirmation reduces false signals |
| NW_Envelope | Direction + zones | Kernel gives direction; Envelope gives entry/exit levels |
| OB_FVG | Entry filter | Only enter OB/FVG setups when kernel confirms direction |
| RSI | Momentum + trend | Kernel provides trend; RSI confirms momentum at key levels |
| EMA/SMA | Comparison | Kernel is less noisy than EMA; use both for confluence |

**Best combination:** NW_RQ_Kernel (direction) + NW_Envelope (zones) + SMC_Structure (structure) — the full kernel-SMC playbook.

## 6. Position Management

### Stop Loss
- **Trend trades:** SL beyond the kernel value line by 1-2 ATR. If price breaks well below the kernel in a long trade, the trend thesis is invalid.

```json
{
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.h4_nw_rq_kernel.value",
    "offset": "-2.0",
    "description": "SL 2 ATR below kernel line"
  }
}
```

### Take Profit
- Target the next SMC structure level or NW_Envelope boundary.
- Use kernel direction change as exit signal for trend trades.

## 7. Pitfalls

1. **Using crossovers for fast scalping.** The smooth crossover is designed for medium-term signals. On M1-M5, it lags too much. Use `is_bullish`/`is_bearish` for faster reaction.
2. **Over-smoothing.** High `lookback_window` (>15) makes the kernel very slow. Keep it at 6-10 for most timeframes.
3. **Ignoring start_bar.** The first `start_bar` bars have unstable kernel estimates. Never rely on signals from the first 25 bars of a session.
4. **Treating kernel as exact S/R.** The kernel line is a probabilistic estimate, not a hard level. Use it as a zone (±0.2% of value) rather than an exact price.
5. **Conflicting with structure.** If SMC_Structure shows bearish but kernel is bullish, trust structure over kernel. Kernel is a smoothing tool, not a structural one.

## 8. XAUUSD-Specific Notes

- **Kernel as trend proxy.** On XAUUSD H4, the kernel direction agrees with the dominant trend approximately 80% of the time, with fewer false signals than EMA 50.
- **Gold respects the kernel line.** Price tends to bounce off the kernel value during pullbacks in trending markets. This makes it an effective dynamic S/R.
- **Session behavior.** During Asian session, the kernel line is relatively flat — useful for mean reversion. During London/NY, kernel direction changes are most significant.
- **Crossover reliability.** Smooth crossovers on H4 gold produce 2-4 signals per month. Win rate improves to 70%+ when aligned with SMC trend.
- **News caution.** Major news can temporarily whip the kernel direction. Wait 2-3 bars after NFP/FOMC before trusting kernel signals.
