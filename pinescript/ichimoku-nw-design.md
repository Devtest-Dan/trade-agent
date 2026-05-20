# Ichimoku Kinko Hyo (Nadaraya–Watson) — Design

**Date:** 2026-05-21
**Target platform:** TradingView, Pine Script v6
**Deliverable:** Single overlay indicator script

## 1. Goal

Build a variant of the classic Ichimoku Kinko Hyo indicator that replaces the
`(highest_high + lowest_low) / 2` midpoint calculation in Tenkan-sen, Kijun-sen,
and Senkou Span B with a Nadaraya-Watson Rational-Quadratic-Kernel-smoothed
midpoint. All other Ichimoku mechanics (Span A derivation, +26 forward
projection of the cloud, -26 Chikou shift) remain identical to the classic
specification so the indicator stays recognisably Ichimoku.

The kernel function is reused verbatim from the jdehorty PineScript script
"Nadaraya-Watson: Rational Quadratic Kernel (Non-Repainting)" (MPL 2.0), so the
script feels native alongside it on charts.

## 2. Mathematical substitution

Classic:

```
tenkan(t) = ( max(high[0..n-1]) + min(low[0..n-1]) ) / 2,   n = 9
kijun(t)  = same with n = 26
spanB(t)  = same with n = 52
```

NWE substitute (Method B — smooth high and low independently, then midpoint):

```
nw_mid(n) = ( kernel_regression(high, n) + kernel_regression(low, n) ) / 2

tenkan(t) = nw_mid(9)
kijun(t)  = nw_mid(26)
spanB(t)  = nw_mid(52)

spanA(t)  = ( tenkan(t) + kijun(t) ) / 2          // unchanged
chikou(t) = close(t)                              // unchanged (shift -26 on plot)
```

`kernel_regression(src, h)` is the jdehorty RQ kernel:

```
w(i) = ( 1 + i² / (2 · r · h²) )^(-r)
kernel_regression(src, h) = Σ src[i] · w(i)  /  Σ w(i)     for i ∈ [0, lookback]
```

`r` (relative weighting, default 8) is a single shared parameter across all
three lines. `lookback` scales with `h` (see §4) so the wider Span B kernel
actually feels its 52-bar window.

## 3. Inputs

### Ichimoku Settings
| Input | Default | Range | Notes |
|---|---|---|---|
| Tenkan length | 9 | 2+ | Bandwidth `h` for Tenkan |
| Kijun length | 26 | 2+ | Bandwidth `h` for Kijun |
| Span B length | 52 | 2+ | Bandwidth `h` for Span B |
| Displacement | 26 | 1+ | Forward shift for Span A/B; backward shift for Chikou |

### Kernel Settings
| Input | Default | Range | Notes |
|---|---|---|---|
| Relative Weighting (r) | 8.0 | 0.25+ | Shared RQ alpha. As r → 0 the kernel becomes more long-term anchored; as r → ∞ it approaches a Gaussian kernel |
| Start Regression at Bar (x_0) | 25 | 0+ | Initial offset; bars 0..x_0 receive low weight |

### Display
Toggles for: Tenkan, Kijun, Span A, Span B, Cloud fill, Chikou, TK cross
markers, Regime tint. All default on.

### Colors
Tenkan, Kijun, Bullish cloud, Bearish cloud, Chikou, Bullish regime tint,
Bearish regime tint.

## 4. Lookback range scaling

jdehorty's original script uses `for i = 0 to size + x_0` where `size = 1`
(from `array.size(array.from(src))`). That gives a fixed loop range of ~26
iterations regardless of `h`. For `h = 8` this is fine — the RQ kernel weights
decay fast enough that bars beyond 26 lag contribute negligibly. But for `h = 52`
the same 26-bar window severely truncates the kernel tails, causing Span B to
look almost identical to Kijun.

We fix this by scaling the loop with bandwidth:

```
lookback = max( 1 + x_0, round(5 · h) )
```

The `5h` constant is conservative — at lag = 5h, RQ kernel weight is
`(1 + 25/(2r))^(-r)` ≈ 0.0008 for r = 8, well below noise floor.
Any `_src[i]` returning `na` (chart history shorter than `lookback`) is skipped.

## 5. Cloud, markers, regime tint

**Kumo:** Span A and Span B are plotted with `offset = displacement` (and
`color = na` to keep the lines invisible), then `fill()` between them paints
the cloud. Cloud color is bullish (green-tinted) when `spanA > spanB`, bearish
(red-tinted) otherwise — computed per bar.

**TK crosses:** `ta.crossover(tenkan, kijun)` and `ta.crossunder(tenkan, kijun)`
produce triangle-up below bar / triangle-down above bar markers respectively.
Cross detection runs on the *current bar's* Tenkan/Kijun — no offset.

**Regime tint:** Subtle full-bar background color based on price vs. the cloud
*as drawn at the current bar*. Because the cloud at bar `t` was computed at
`t − displacement`, the comparison uses `spanA[displacement]` and
`spanB[displacement]`:

```
top    = max(spanA[disp], spanB[disp])
bottom = min(spanA[disp], spanB[disp])
above_cloud = close > top
below_cloud = close < bottom
// inside cloud: no tint
```

This matches the traditional Ichimoku interpretation: regime is read off the
visible cloud at the current bar.

## 6. Non-repaint guarantee

| Output | Why non-repainting |
|---|---|
| Tenkan, Kijun, Span B | `kernel_regression` weights only past bars (`src[i]`, i ≥ 0). Locked at bar close. |
| Span A | Derived from confirmed Tenkan + Kijun. Forward shift +26 is a display offset; the value drawn at `t+26` was computed at `t` and never changes. |
| Chikou | Backward shift only; the value at any drawn position is just today's close. Cannot be traded retroactively but does not repaint. |
| TK cross markers | Fire on `ta.crossover` at bar close. Locked. |
| Regime tint | Uses fully historical `close`, `spanA[disp]`, `spanB[disp]`. Locked at bar close. |

No `barstate.isconfirmed` gating is used — the math is already confirmed-safe.

## 7. Performance

Three NW lines × 2 kernel calls each (high + low) = 6 kernel calls per bar.
With `lookback = round(5h)`:

| Line | Lookback | Per-bar ops |
|---|---|---|
| Tenkan (h=9) | 45 | 90 |
| Kijun (h=26) | 130 | 260 |
| Span B (h=52) | 260 | 520 |
| **Total** | | **≈ 870** |

Linear in chart length. A 5000-bar chart costs ~4.3M ops, well within
TradingView's per-script execution budget. `max_bars_back = 500` is declared
on the `indicator()` call as safety.

## 8. Alerts

Two `alertcondition()` calls — TK bullish cross and TK bearish cross. Free to
add, no runtime cost, gives the user the option to wire TradingView alerts.

## 9. File layout

Single file: `D:\trade-agent\pinescript\ichimoku-nw.pine`

Sections in order:
1. License header (attribution to jdehorty for RQ kernel; MPL 2.0)
2. `//@version=6` + `indicator(...)` declaration
3. Inputs (4 groups: Ichimoku, Kernel, Display, Colors)
4. `kernel_regression(_src, _h)` helper
5. `nw_mid(_h)` helper
6. Compute tenkan, kijun, spanA, spanB
7. Plots: Tenkan, Kijun, Span A (offset), Span B (offset), fill, Chikou (offset)
8. `plotshape` for TK crosses
9. `bgcolor` for regime tint
10. `alertcondition` for TK crosses

## 10. Out of scope

- Per-line `r` parameter (single shared `r` only)
- Replacement of Chikou or projection mechanics (kept classic)
- Multi-timeframe rendering (chart timeframe only)
- Trading-strategy/backtest packaging (this is an indicator, not a strategy)
- Trade-agent Python port (separate cycle if ever needed)
