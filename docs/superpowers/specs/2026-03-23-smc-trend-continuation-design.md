# SMC Trend Continuation Strategy — Design Spec

**Symbol:** EURUSD
**Style:** Flexible (setup-driven, no session constraint)
**Date:** 2026-03-23

## Overview

A trend-continuation playbook that uses H4 Smart Money Concepts for directional bias and key zones, M15 Nadaraya-Watson Envelope for pullback detection, and M15 RSI Kernel for momentum-based entry triggers. Exits are SMC-driven with NWE-based trailing.

The phase machine is split into separate long/short paths because `TradeAction.direction` is a static literal in the playbook schema — it cannot be set dynamically from a variable.

## Indicators

| ID | Indicator | Timeframe | Role | Key Parameters |
|----|-----------|-----------|------|----------------|
| `h4_smc` | SMC_Structure (v2.14) | H4 | Directional bias, OB/FVG zones, premium/discount | `swing_len: 10` |
| `m15_nwe` | NW_Envelope | M15 | Pullback detection — price reaching value bands | `lookback_window: 8, relative_weighting: 8.0, start_bar: 25, atr_length: 60, near_factor: 1.5, far_factor: 8.0` |
| `m15_rsi_kernel` | RSI_Kernel | M15 | Momentum trigger — RSI/kernel crossovers | `rsi_length: 14, kernel_lookback: 8, kernel_weight: 8.0, ob_level: 70, os_level: 30` |
| `h4_atr` | ATR | H4 | SL/TP fallback sizing, trailing step | `length: 14` |

## Entry Conditions

### Long Entry

All conditions must be true (AND):

1. **H4 SMC trend is bullish** — `ind.h4_smc.trend == 1.0`
2. **H4 SMC zone is discount** — `ind.h4_smc.zone == -1.0` (price below equilibrium)
3. **M15 NWE pullback to lower band** — `_price <= ind.m15_nwe.lower_near`
4. **M15 RSI Kernel momentum trigger** — `ind.m15_rsi_kernel.rsi_cross_above == 1.0`

### Short Entry

All conditions must be true (AND):

1. **H4 SMC trend is bearish** — `ind.h4_smc.trend == -1.0`
2. **H4 SMC zone is premium** — `ind.h4_smc.zone == 1.0` (price above equilibrium)
3. **M15 NWE pullback to upper band** — `_price >= ind.m15_nwe.upper_near`
4. **M15 RSI Kernel momentum trigger** — `ind.m15_rsi_kernel.rsi_cross_below == 1.0`

## Exit / Risk Management

### Stop Loss

- **Primary (longs):** SL = `ind.h4_smc.ob_lower`, but only when `ind.h4_smc.ob_type == 1.0` (bullish OB) AND `ind.h4_smc.ob_lower < _price`. Otherwise use fallback.
- **Primary (shorts):** SL = `ind.h4_smc.ob_upper`, but only when `ind.h4_smc.ob_type == -1.0` (bearish OB) AND `ind.h4_smc.ob_upper > _price`. Otherwise use fallback.
- **Fallback:** ATR-based SL: `_price - ind.h4_atr.value * 2.0` for longs, `_price + ind.h4_atr.value * 2.0` for shorts.

### Take Profit

Conditional chain (first match wins):

**Longs:**
1. If `ind.h4_smc.fvg_type == -1.0` (bearish FVG exists above): TP = `ind.h4_smc.fvg_upper`
2. Else if `ind.h4_smc.ob_type == -1.0` (bearish OB exists above): TP = `ind.h4_smc.ob_lower`
3. Else: TP = `_price + ind.h4_atr.value * 3.0`

**Shorts:**
1. If `ind.h4_smc.fvg_type == 1.0` (bullish FVG exists below): TP = `ind.h4_smc.fvg_lower`
2. Else if `ind.h4_smc.ob_type == 1.0` (bullish OB exists below): TP = `ind.h4_smc.ob_upper`
3. Else: TP = `_price - ind.h4_atr.value * 3.0`

### Trailing Stop (via `modify_sl`, not `trail_sl`)

Uses `modify_sl` with `continuous: true` to set SL directly to an absolute NWE band level, avoiding the `trail_sl` distance-from-price mechanic which doesn't suit band-based trailing.

- **Activation condition:** `trade.pnl > ind.h4_atr.value * 1.5`
- **Longs:** Set SL to `ind.m15_nwe.lower_near` (only if `ind.m15_nwe.lower_near > trade.sl` — never widen SL)
- **Shorts:** Set SL to `ind.m15_nwe.upper_near` (only if `ind.m15_nwe.upper_near < trade.sl` — never widen SL)
- **Continuous:** Re-evaluated on every M15 bar

### Breakeven Protection

- **Once, when** `trade.pnl > ind.h4_atr.value * 1.0`: move SL to `trade.open_price` (breakeven)

## Phase Machine

```
idle ──┬── scanning_long ── entry_ready_long ── in_trade_long ──┐
       │                                                         │
       └── scanning_short ── entry_ready_short ── in_trade_short ┘
                                                                 │
                                                          back to idle
```

### Phase: `idle`

- **Evaluate on:** `["H4"]`
- **Transition to `scanning_long`** (priority 1):
  - `ind.h4_smc.trend == 1.0` AND `ind.h4_smc.zone == -1.0`
- **Transition to `scanning_short`** (priority 2):
  - `ind.h4_smc.trend == -1.0` AND `ind.h4_smc.zone == 1.0`

### Phase: `scanning_long`

- **Evaluate on:** `["M15", "H4"]`
- **Transition to `entry_ready_long`** (priority 1):
  - `_price <= ind.m15_nwe.lower_near`
- **Transition back to `idle`** (priority 2):
  - `ind.h4_smc.trend != 1.0` OR `ind.h4_smc.zone != -1.0` (bias invalidated)
- **Timeout:** 200 bars on M15 → back to `idle`

### Phase: `scanning_short`

- **Evaluate on:** `["M15", "H4"]`
- **Transition to `entry_ready_short`** (priority 1):
  - `_price >= ind.m15_nwe.upper_near`
- **Transition back to `idle`** (priority 2):
  - `ind.h4_smc.trend != -1.0` OR `ind.h4_smc.zone != 1.0` (bias invalidated)
- **Timeout:** 200 bars on M15 → back to `idle`

### Phase: `entry_ready_long`

- **Evaluate on:** `["M15", "H4"]`
- **Transition to `in_trade_long`** (priority 1):
  - `ind.m15_rsi_kernel.rsi_cross_above == 1.0`
  - **Actions:**
    - Calculate SL: OB-based if `ind.h4_smc.ob_type == 1.0` AND `ind.h4_smc.ob_lower < _price`, else `_price - ind.h4_atr.value * 2.0`
    - Calculate TP: FVG/OB conditional chain (see Exit section)
    - `open_trade`: direction = `"BUY"`, lot = `risk.max_lot`, sl = `var.initial_sl`, tp = `var.initial_tp`
- **Transition back to `scanning_long`** (priority 2):
  - `_price > ind.m15_nwe.yhat` (price returned above midline without triggering)
- **Transition back to `idle`** (priority 3):
  - `ind.h4_smc.trend != 1.0` (bias invalidated)
- **Timeout:** 50 bars on M15 → back to `scanning_long`

### Phase: `entry_ready_short`

- **Evaluate on:** `["M15", "H4"]`
- **Transition to `in_trade_short`** (priority 1):
  - `ind.m15_rsi_kernel.rsi_cross_below == 1.0`
  - **Actions:**
    - Calculate SL: OB-based if `ind.h4_smc.ob_type == -1.0` AND `ind.h4_smc.ob_upper > _price`, else `_price + ind.h4_atr.value * 2.0`
    - Calculate TP: FVG/OB conditional chain (see Exit section)
    - `open_trade`: direction = `"SELL"`, lot = `risk.max_lot`, sl = `var.initial_sl`, tp = `var.initial_tp`
- **Transition back to `scanning_short`** (priority 2):
  - `_price < ind.m15_nwe.yhat` (price returned below midline without triggering)
- **Transition back to `idle`** (priority 3):
  - `ind.h4_smc.trend != -1.0` (bias invalidated)
- **Timeout:** 50 bars on M15 → back to `scanning_short`

### Phase: `in_trade_long`

- **Evaluate on:** `["M15", "H4"]`
- **Position management:**
  - **Breakeven** (`once: true`): when `trade.pnl > ind.h4_atr.value * 1.0` → `modify_sl` to `trade.open_price`
  - **NWE trailing** (`continuous: true`): when `trade.pnl > ind.h4_atr.value * 1.5` AND `ind.m15_nwe.lower_near > trade.sl` → `modify_sl` to `ind.m15_nwe.lower_near`
- **Transition to `idle`:**
  - `on_trade_closed` (SL/TP hit)
  - `ind.h4_smc.choch_bear == 1.0` → close trade immediately (trend reversal)
- **Timeout:** 500 bars on M15 (~5.2 days) → close trade, back to `idle`

### Phase: `in_trade_short`

- **Evaluate on:** `["M15", "H4"]`
- **Position management:**
  - **Breakeven** (`once: true`): when `trade.pnl > ind.h4_atr.value * 1.0` → `modify_sl` to `trade.open_price`
  - **NWE trailing** (`continuous: true`): when `trade.pnl > ind.h4_atr.value * 1.5` AND `ind.m15_nwe.upper_near < trade.sl` → `modify_sl` to `ind.m15_nwe.upper_near`
- **Transition to `idle`:**
  - `on_trade_closed` (SL/TP hit)
  - `ind.h4_smc.choch_bull == 1.0` → close trade immediately (trend reversal)
- **Timeout:** 500 bars on M15 (~5.2 days) → close trade, back to `idle`

## Autonomy

Configurable per instance:
- `signal_only` — Emit signal, no trade execution
- `semi_auto` — Open trade automatically, manual close
- `full_auto` — Fully automated (default for backtesting)

## Risk Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_lot` | 0.1 | Maximum lot size per trade |
| `max_daily_trades` | 3 | Maximum trades per day |
| `max_open_positions` | 1 | Only one position at a time |
| `max_drawdown_pct` | 5.0 | Circuit breaker — stop trading if daily drawdown exceeds 5% |

## Variables

| Name | Type | Default | Purpose |
|------|------|---------|---------|
| `initial_sl` | float | 0.0 | Calculated SL at entry |
| `initial_tp` | float | 0.0 | Calculated TP at entry |

## Future Optimization

After backtesting, potential additions:
- MACD 4C momentum filter
- Session filter (London/NY overlap)
- ADX trending filter
- Partial close at 1:1 R:R before trailing
- Multi-symbol expansion
