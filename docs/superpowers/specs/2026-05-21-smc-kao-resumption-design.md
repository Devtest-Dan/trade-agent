# SMC KAO Resumption Strategy — Design Spec

**Date:** 2026-05-21
**Author:** Daniel (brainstormed with Claude)
**Target:** Pine Script v6 strategy for TradingView, deployed via TradingView Desktop
**Status:** Design — awaiting user review before implementation plan

---

## 1. Concept

Trade the **second impulse** of the impulse-correction-impulse cycle. Enter in the direction of the active SMC trend, when price has retraced into the discount/premium zone of the current impulse leg AND the Kernel Bollinger Band's outer band rejects price with a wick (correction exhaustion signal).

The strategy treats the CHoCH-only case (first impulse after trend flip, no subsequent BoS) identically to the BoS-confirmed case. The CHoCH alone establishes trend; entries become valid as soon as price retraces beyond 50% of the new impulse leg.

---

## 2. State Machine

Maintained per bar (computed on `barstate.isconfirmed`):

| Variable | Type | Meaning |
|---|---|---|
| `trendDir` | int | `+1` bull / `−1` bear / `0` none. Flipped only by opposite-direction major CHoCH. |
| `legHigh` | float | Highest high since `trendDir` was last set. |
| `legLow` | float | Lowest low since `trendDir` was last set. |
| `legMid` | float | `(legHigh + legLow) / 2` — equilibrium / 50% level. |
| `inDiscount` (bull) | bool | `close < legMid` AND `low <= legMid`. |
| `inDiscount` (bear / premium) | bool | `close > legMid` AND `high >= legMid`. |
| `armed` | bool | Re-entry gate. True if no open position AND not blocked by re-arm rules. |
| `barsInTrend` | int | Count since `trendDir` last changed. Used to skip entries in degenerate (flat) early-trend bars. |

### 2.1 Reset / re-arm rules (after each entry)

`armed` becomes `false` on entry. Re-arms (becomes `true` again) on next bar where either:

- **Extreme extension:** `legHigh` makes a new high (bull) / `legLow` makes a new low (bear), OR
- **Basis touch:** `low <= kbb.basis` (bull) / `high >= kbb.basis` (bear)

Both checks active simultaneously by default — if EITHER condition triggers, `armed` flips back to true (OR-logic). Each can be toggled off via input. If both are toggled off, `armed` never re-arms and the strategy becomes "one entry per trend" (valid configuration, just more conservative).

---

## 3. Entry Triggers

### 3.1 Long entry (all conditions on the same confirmed bar)
1. `trendDir == +1`
2. `armed == true`
3. `barsInTrend >= 5` (configurable)
4. `low < legMid` — bar dipped into discount zone
5. `low < kbb.lower` AND `close > kbb.lower` — wick pierced lower band, closed back inside
6. `close > open` — positive body (rejection candle)
7. `kbb.lower` is not NaN

### 3.2 Short entry (mirror)
1. `trendDir == −1`
2. `armed == true`
3. `barsInTrend >= 5`
4. `high > legMid` — bar pushed into premium zone
5. `high > kbb.upper` AND `close < kbb.upper` — wick pierced upper band, closed back inside
6. `close < open` — negative body
7. `kbb.upper` is not NaN

### 3.3 Direction filter
- `Direction` input ∈ {Both, Long only, Short only}. Filters which side fires regardless of trend.

### 3.4 Pyramiding
- `strategy()` declared with `pyramiding = 1` — only one open position at a time. Concurrent long+short never happens.

---

## 4. Exit Logic

Priority order each bar (first matching exit fires):

### 4.1 Hard stop loss (frozen at entry)
- **Long:** SL = `legLow_at_entry − buffer`. Exits if `low <= SL`.
- **Short:** SL = `legHigh_at_entry + buffer`. Exits if `high >= SL`.
- `buffer` = `input.float(0.0, "SL buffer (price units)", min = 0.0)` — default 0; widen for noisy symbols (e.g., XAUUSD).
- Frozen: SL does NOT update even if `legLow`/`legHigh` change during trade.

### 4.2 Structural trailing stop ("live-updating" extreme tracking)
After entry, each **confirmed pivot** (same major pivot logic as KAO_v1.7) sets a new trail level:
- **Long:** trail initialized to the hard SL (`legLow_at_entry − buffer`). Each confirmed pivot LOW above entry price → `trail = max(trail, pivot_low)`. Exits if `low <= trail`.
- **Short:** trail initialized to the hard SL (`legHigh_at_entry + buffer`). Each confirmed pivot HIGH below entry price → `trail = min(trail, pivot_high)`. Exits if `high >= trail`.

The trail subsumes the hard SL — they share the same level variable. The trail only ratchets in the direction of profit. Pivots that don't satisfy the "above entry" / "below entry" guard are ignored, so an adverse pivot can never loosen the stop.

This captures runaway 2nd-impulse moves by ratcheting under each new HL (long) or above each new LH (short), and exits at the first structural break.

### 4.3 Opposite-direction CHoCH (force-close)
If a bearish major CHoCH fires while long → close at bar close immediately. Mirror for short.

### 4.4 No fixed TP
Trail + opposite-CHoCH handle profit-taking; a frozen TP would conflict with the "live-updating extreme" intent.

---

## 5. Position Sizing

```
risk_pct   = input.float(1.0, "Risk % per trade", 0.1, 5.0)
risk_dist  = abs(entry_price - initialSL)            // per-unit risk
qty        = (strategy.equity * risk_pct / 100) / risk_dist
strategy.entry(id, dir, qty = qty)
```

For symbols where Pine's price units don't equal currency-per-contract (forex pip values, futures point values), document the caveat: strategy tester PnL is in chart's price units × qty; for accurate forex backtesting, set `default_qty_type = strategy.fixed` and use the lot calculator separately, OR convert via mintick.

---

## 6. Inputs

### 6.1 Structure (passed to ported KAO_v1.7 code)
- All KAO_v1.7 swing/internal pivot lengths, OB/FVG toggles, etc., preserved with KAO defaults.

### 6.2 Kernel Bollinger Band (ported)
- KBB length, std-dev multiplier, kernel bandwidth, source — all KBB inputs preserved with current defaults.

### 6.3 Strategy
| Input | Type | Default | Range |
|---|---|---|---|
| Direction | enum | Both | Both / Long only / Short only |
| Risk % per trade | float | 1.0 | 0.1 .. 5.0 |
| SL buffer (price units) | float | 0.0 | ≥ 0 |
| Min bars in new trend before entry | int | 5 | 1 .. 100 |
| Re-arm on new HH/LL extreme | bool | true | — |
| Re-arm on basis touch | bool | true | — |

### 6.4 Visuals
- Show legHigh / legLow lines (default on)
- Show legMid (50%) line (default on)
- Show discount/premium zone box (default on)
- Show entry/exit markers (default on)
- All KAO_v1.7 visual toggles preserved with KAO defaults

---

## 7. Plots (numeric, for data window / future cross-script consumption)

| Plot title | Series |
|---|---|
| `trendDir` | `+1` / `−1` / `0` |
| `legHigh` | float |
| `legLow` | float |
| `legMid` | float |
| `armed` | `1` / `0` |
| `kbb_basis`, `kbb_upper`, `kbb_lower` | float (preserved from KBB) |
| All KAO_v1.7 existing plots | preserved |

---

## 8. Alerts

Five alert conditions, all firing `alert.freq_once_per_bar_close`:

1. **Long entry signal** — message: `LONG entry {symbol} {tf} @ {price}, SL {sl}`
2. **Short entry signal** — message: `SHORT entry {symbol} {tf} @ {price}, SL {sl}`
3. **Long exit** — message: `LONG exit {symbol} {tf} @ {price}, reason {SL|TRAIL|CHOCH}`
4. **Short exit** — message: `SHORT exit {symbol} {tf} @ {price}, reason {SL|TRAIL|CHOCH}`
5. **CHoCH detected** (informational) — message: `CHoCH {bull|bear} {symbol} {tf} @ {price}`

---

## 9. File & Naming

- **Script name:** `SMC_KAO_Resumption_Strategy`
- **Title:** `SMC KAO Resumption Strategy v1.0`
- **Version:** `//@version=6`
- **Declaration:** `strategy(...)` (not `indicator(...)`)
- **Local source backup:** `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`
- **Commit:** committed to `trade-agent` repo on creation.

---

## 10. Build Sequence

1. **Port KAO_v1.7 core** — copy full SMC structure detection (BOS/CHoCH/HH/HL/LL/LH, OB, FVG) from `SMC_Structure_OBFVG_KAO` (the v1.7 script). Strip nothing visual; keep all KAO inputs with current defaults.
2. **Port Kernel Bollinger Band** — copy KBB calculation from `Kernel Bollinger Band` (script ID `USER;002961e1925a46fead23d63d3782b84d`). Preserve all inputs.
3. **Add state machine** — `trendDir`, `legHigh`, `legLow`, `legMid`, `armed`, `barsInTrend`, reset rules. Plot all to data window.
4. **Add entry logic** — long/short condition sets, edge-case guards.
5. **Add exit logic** — frozen SL, structural trail using confirmed pivots, opposite-CHoCH force-close.
6. **Add position sizing** — risk-% based qty calculation, plumb into `strategy.entry()`.
7. **Add alerts** — 5 alert conditions with descriptive messages.
8. **Visual layer** — leg lines, discount/premium zone box, entry/exit shapes.

---

## 11. Verification Protocol

**TradingView free-plan constraint: max 2 indicators per chart.** The strategy itself counts as 1 slot. Visual parity checks must therefore be done **sequentially**, not by simultaneous overlay.

### Per-step verification

- **After step 1:** Remove Kernel BB from chart (1 indicator slot used by KAO_v1.7 + 1 free). Load draft strategy. Use `data_get_pine_labels` / `data_get_pine_lines` to extract structure labels from BOTH scripts (one at a time — load KAO_v1.7 alone, capture; load draft alone, capture; diff). All BOS/CHoCH/HH/HL/LL/LH labels must match in price and bar position.
- **After step 2:** Same swap procedure for Kernel BB. Compare `Basis` / `Upper` / `Lower` values via `data_get_study_values` — must match KBB indicator within mintick rounding.
- **After step 3:** Scrub through history with the strategy loaded alone. Manually verify `legHigh` / `legLow` reset at each major CHoCH, and `legMid` is between them.
- **After step 4:** Confirm entry shape markers appear only on bars that satisfy all 5 (long) / 5 (short) conditions.
- **After step 5–6:** Open Strategy Tester. On EURUSD H1 (current chart), inspect first 5 trades manually — verify each entry passes all conditions and each exit fired for the correct reason.

### Final symbol/TF sweep

Per memory, current trade-agent best 6-symbol portfolio uses **EU / GJ / GU / UJ / EJ / XAU**. Run the strategy on each on H1 first, then H4. Record per-symbol:
- Profit Factor
- Win rate %
- Max Drawdown %
- Total trades
- Avg trade R-multiple

Baseline target (informal, not a gate): PF > 1.3 on at least 4/6 symbols. Below that → tune pivot length / KBB params before code changes.

### Visual parity caveat

If sequential capture diff shows the ported KAO labels differ from `SMC_Structure_OBFVG_KAO`, the cause is almost certainly a pivot-confirmation lag difference (left/right pivot params). Fix by matching the exact `ta.pivothigh(left, right)` parameters used in v1.7 — do not redesign structure logic.

---

## 12. Out of Scope (v2 candidates)

- HTF trend confirmation (H4/D1 trend filter for H1 entries)
- Multi-symbol screener / scanner
- Webhook JSON alert payloads (v1 = text alerts only)
- TPO / OB / FVG entry filters (structure code captures these but they don't gate entries in v1)
- Per-symbol auto-tuned inputs
- Walk-forward / optimization harness

---

## 13. Open Questions Resolved During Brainstorming

| Question | Resolution |
|---|---|
| BB wick interpretation | Wick rejection (poke beyond, close inside) |
| Discount/premium anchor | Highest high / lowest low SINCE TREND STARTED (last opposite CHoCH) |
| Exit philosophy | Swing-based SL + structural trail + opposite-CHoCH force-close, no fixed TP |
| Re-entries per trend | Multiple, gated by extension-or-basis-touch re-arm |
| Direction & sizing | Both directions, fixed risk % (default 1%) |
| TF | Single chart TF (H1 default) |
| TP interpretation | Reframed as structural trail ratcheting under each new HL / above each new LH |
| KAO integration | Combined indicator+strategy in one file (full KAO_v1.7 port) |
| TV plan | Free plan — verification uses sequential indicator loads, max 2 slots |
