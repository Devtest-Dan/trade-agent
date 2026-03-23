# Mean-Reversion + Divergence Strategy — Design Spec

**Symbols:** EURUSD, GBPJPY (lot 1.0) | XAUUSD longs only (lot 0.2)
**Date:** 2026-03-23
**Variant:** A — H4 structure + M15 entry

## Overview

A mean-reversion strategy that fades overextended price moves confirmed by divergence. Enters when price reaches NWE outer bands (overextended), Kernel Divergence confirms the move is exhausting, and RSI Kernel confirms the extreme. Targets the NWE midline (yhat) as the reversion target. Trails SL using NWE bands as price reverts.

SMC provides zone confirmation (premium/discount) and BOS danger filtering, but is toggleable for testing without structural filters.

## Indicators (5)

| ID | Indicator | Timeframe | Role | Key Parameters |
|----|-----------|-----------|------|----------------|
| `h4_smc` | SMC_Structure v2.14 | H4 | Zone filter + BOS danger check (toggleable) | `swing_len: 10` |
| `m15_nwe` | NW_Envelope | M15 | Extreme detection (outer bands) + TP target (yhat) + trailing (avg bands) | `lookback_window: 8, relative_weighting: 8.0, start_bar: 25, atr_length: 60, near_factor: 1.5, far_factor: 8.0` |
| `m15_kernel_div` | Kernel_Div | M15 | Entry trigger — bullish/bearish regular divergence | default params |
| `m15_rsi_kernel` | RSI_Kernel | M15 | Overbought/oversold confirmation | `rsi_length: 7, kernel_lookback: 8, kernel_weight: 8.0, ob_level: 70, os_level: 30` |
| `h4_atr` | ATR | H4 | SL buffer sizing | `period: 14` |

## Entry Conditions

### Short Entry (fade bullish extreme)

All conditions AND:

1. **M15 NWE price at upper extreme** — `_price >= ind.m15_nwe.upper_avg` (price at or beyond upper average band)
2. **M15 Kernel Divergence bearish regular** — `ind.m15_kernel_div.bear_reg_div == 1.0` (price higher high, oscillator lower high — momentum exhausting)
3. **M15 RSI Kernel overbought** — `ind.m15_rsi_kernel.overbought == 1.0` (RSI > 70, extreme confirmed)
4. **H4 SMC zone is premium** — `ind.h4_smc.zone == 1.0` *[toggleable — remove for no-SMC variant]*
5. **H4 SMC no fresh bullish BOS** — `ind.h4_smc.bos_bull != 1.0` (not a strong trend breakout) *[toggleable]*

### Long Entry (fade bearish extreme)

All conditions AND:

1. **M15 NWE price at lower extreme** — `_price <= ind.m15_nwe.lower_avg` (price at or beyond lower average band)
2. **M15 Kernel Divergence bullish regular** — `ind.m15_kernel_div.bull_reg_div == 1.0` (price lower low, oscillator higher low — selling exhausting)
3. **M15 RSI Kernel oversold** — `ind.m15_rsi_kernel.oversold == 1.0` (RSI < 30, extreme confirmed)
4. **H4 SMC zone is discount** — `ind.h4_smc.zone == -1.0` *[toggleable]*
5. **H4 SMC no fresh bearish BOS** — `ind.h4_smc.bos_bear != 1.0` *[toggleable]*

## Exit / Risk Management

### Stop Loss

- **Shorts:** `ind.m15_nwe.upper_far + ind.h4_atr.value * 1.0` (beyond the outermost band + ATR buffer)
- **Longs:** `ind.m15_nwe.lower_far - ind.h4_atr.value * 1.0`
- If price extends past the far band + buffer, the mean-reversion thesis is invalid

### Take Profit

- **Target:** `ind.m15_nwe.yhat` (NWE kernel midline — the "mean" we're reverting to)
- Mean-reversion TP is the regression line itself — this is where price naturally gravitates

### Breakeven

- **Shorts:** When `trade.open_price - _price > ind.h4_atr.value * 0.5` → SL to `trade.open_price`
- **Longs:** When `_price - trade.open_price > ind.h4_atr.value * 0.5` → SL to `trade.open_price`
- Earlier breakeven than trend strategy (0.5x vs 1.5x) because mean-reversion moves are smaller
- Uses computed profit expression (not `trade.pnl`) to avoid executor dependency

### Trailing Stop (Approach B)

- **Shorts activation:** `trade.open_price - _price > ind.h4_atr.value * 1.0`
- **Shorts trail:** SL to `ind.m15_nwe.upper_avg` when `ind.m15_nwe.upper_avg < trade.sl` (tighten only)
- **Longs activation:** `_price - trade.open_price > ind.h4_atr.value * 1.0`
- **Longs trail:** SL to `ind.m15_nwe.lower_avg` when `ind.m15_nwe.lower_avg > trade.sl` (tighten only)
- Uses `modify_sl` — only tightens, never widens
- As price reverts toward yhat, the avg band follows, protecting profits

## Phase Machine (5 phases)

```
idle ──┬── watching_short ── in_trade_short ──→ watching_short (re-entry)
       └── watching_long ── in_trade_long ──→ watching_long (re-entry)
```

Mean-reversion doesn't need separate scanning + entry_ready phases. The setup is: extreme detected + divergence + RSI extreme, all checked simultaneously.

### Phase: `idle`

- **Evaluate on:** `["M15"]`
- **To `watching_short`** (priority 2): `_price >= ind.m15_nwe.upper_avg`
- **To `watching_long`** (priority 1): `_price <= ind.m15_nwe.lower_avg`

### Phase: `watching_short`

- **Evaluate on:** `["M15", "H4"]`
- **To `in_trade_short`** (priority 3, all AND):
  - `ind.m15_kernel_div.bear_reg_div == 1.0` (divergence fires)
  - `ind.m15_rsi_kernel.overbought == 1.0` (RSI extreme)
  - `ind.h4_smc.zone == 1.0` (premium zone) *[toggleable]*
  - `ind.h4_smc.bos_bull != 1.0` (no fresh BOS) *[toggleable]*
- **Actions on entry:**
  - `set_var initial_sl` = `ind.m15_nwe.upper_far + ind.h4_atr.value * 1.0`
  - `set_var initial_tp` = `ind.m15_nwe.yhat`
  - `open_trade`: direction="SELL", sl=`var.initial_sl`, tp=`var.initial_tp`
- **Back to `idle`** (priority 2): `_price < ind.m15_nwe.upper_near` (no longer at extreme)
- **Back to `idle`** (priority 1): `ind.h4_smc.bos_bull == 1.0` (fresh BOS — danger) *[toggleable]*
- **Timeout:** 100 M15 bars (~25 hours) → idle

### Phase: `watching_long`

- **Evaluate on:** `["M15", "H4"]`
- **To `in_trade_long`** (priority 3, all AND):
  - `ind.m15_kernel_div.bull_reg_div == 1.0`
  - `ind.m15_rsi_kernel.oversold == 1.0`
  - `ind.h4_smc.zone == -1.0` *[toggleable]*
  - `ind.h4_smc.bos_bear != 1.0` *[toggleable]*
- **Actions on entry:**
  - `set_var initial_sl` = `ind.m15_nwe.lower_far - ind.h4_atr.value * 1.0`
  - `set_var initial_tp` = `ind.m15_nwe.yhat`
  - `open_trade`: direction="BUY", sl=`var.initial_sl`, tp=`var.initial_tp`
- **Back to `idle`** (priority 2): `_price > ind.m15_nwe.lower_near`
- **Back to `idle`** (priority 1): `ind.h4_smc.bos_bear == 1.0` *[toggleable]*
- **Timeout:** 100 M15 bars → idle

### Phase: `in_trade_short`

- **Evaluate on:** `["M15", "H4"]`
- **Position management:**
  1. **Breakeven** (once): `trade.open_price - _price > ind.h4_atr.value * 0.5` → `modify_sl` to `trade.open_price`
  2. **NWE trailing** (continuous): `trade.open_price - _price > ind.h4_atr.value * 1.0` AND `ind.m15_nwe.upper_avg < trade.sl` → `modify_sl` to `ind.m15_nwe.upper_avg`
- **Exit transition to `idle`** (priority 1):
  - `ind.h4_smc.bos_bull == 1.0` → `actions: [{close_trade: true}]` (trend breakout invalidates mean-reversion) *[toggleable]*
- **Timeout:** 200 M15 bars (~2.1 days) → `actions: [{close_trade: true}]`, transition to `idle`
- **On trade closed:** → `watching_short` (re-entry)

Note: If BOS exit fires, it transitions to `idle` with `close_trade`. The `on_trade_closed` callback fires from `idle` (not `in_trade_short`) so re-entry does not trigger — this is correct because BOS means the trend is strong and we should stop fading.

### Phase: `in_trade_long`

- **Evaluate on:** `["M15", "H4"]`
- **Position management:**
  1. **Breakeven** (once): `_price - trade.open_price > ind.h4_atr.value * 0.5` → `modify_sl` to `trade.open_price`
  2. **NWE trailing** (continuous): `_price - trade.open_price > ind.h4_atr.value * 1.0` AND `ind.m15_nwe.lower_avg > trade.sl` → `modify_sl` to `ind.m15_nwe.lower_avg`
- **Exit transition to `idle`** (priority 1):
  - `ind.h4_smc.bos_bear == 1.0` → `actions: [{close_trade: true}]` *[toggleable]*
- **Timeout:** 200 M15 bars (~2.1 days) → `actions: [{close_trade: true}]`, transition to `idle`
- **On trade closed:** → `watching_long` (re-entry)

## SMC Toggle

To test without SMC (approach C), create a `_nosmc` variant:
- Remove zone check from `watching_short` and `watching_long` entry conditions
- Remove BOS check from entry conditions
- Remove BOS exit transitions from `in_trade_short` and `in_trade_long`
- Remove BOS danger transitions from `watching_short` and `watching_long`
- Keep `h4_smc` indicator in config (no harm, just unused)

## Risk Configuration

| Parameter | FX Majors | XAUUSD |
|-----------|-----------|--------|
| max_lot | 1.0 | 0.2 |
| max_daily_trades | 5 | 5 |
| max_open_positions | 1 | 1 |
| max_drawdown_pct | 5.0 | 5.0 |

## Variables

| Name | Type | Default | Purpose |
|------|------|---------|---------|
| `initial_sl` | float | 0.0 | SL calculated at entry (auto-populated by engine) |
| `initial_tp` | float | 0.0 | TP calculated at entry — yhat (auto-populated by engine) |

## XAUUSD Variant

- **Longs only** — based on learnings from trend strategy, gold shorts underperform
- **Lot 0.2** — gold volatility requires smaller position size
- Short transitions removed from idle phase
- `watching_short` and `in_trade_short` phases removed entirely (no dead states)

## Future Variants (planned)

- **Variant B:** H1 structure + M15/M5 entry — faster cycles, more trades
- **Variant C:** M15 structure + M5 entry — scalp-style mean-reversion
- **No-SMC variant:** Same logic with SMC conditions removed — for A/B comparison

## Key Design Decisions

1. **NWE upper_avg not upper_far for entry:** upper_far is too extreme and rare. upper_avg catches more setups while still being meaningfully overextended.
2. **Divergence as trigger, not filter:** Divergence is the actual entry signal (it fires on a specific bar). NWE extreme and RSI are the location/confirmation filters.
3. **TP at yhat, not near band:** yhat is the true mean of the kernel regression. near_band is still above the mean and may not be reached in weak reversions.
4. **Trailing with avg band, not near band:** avg band gives enough room for the reversion to play out without getting stopped prematurely.
5. **Shorter timeouts than trend strategy:** Mean-reversion should happen within hours, not days. 100 bars for watching (~25h), 200 for in_trade (~2.1 days).
6. **Re-entry to watching:** Same learning as trend strategy — if conditions persist, look for next setup immediately. Exception: BOS exit goes to `idle` (not re-entry) because BOS invalidates the mean-reversion thesis.
7. **Computed profit, not trade.pnl:** Breakeven and trailing use `trade.open_price - _price` (shorts) / `_price - trade.open_price` (longs) instead of `trade.pnl` to avoid dependency on executor state.
8. **Timeout closes the trade:** Unlike trend strategy where timeout just transitions, mean-reversion timeout includes `close_trade` because a trade still open after 2.1 days has failed its thesis.
