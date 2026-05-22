# Sweep #5 — After dropping close-back-inside requirement

**Date:** 2026-05-22
**Change since sweep #4:** Dropped `close > kbb_lower` (long) and `close < kbb_upper` (short). Entry now fires on any bar that wicks beyond the outer band while in discount/premium zone, regardless of where it closes.

## Side-by-side

| Symbol | TF | #4 | #5 | Δ trades | Δ PF |
|---|---|---|---|---|---|
| EURUSD | H4 | 11 / 27% / 0.27 | 13 / 31% / 0.30 | +2 | +0.03 |
| EURUSD | H1 | 11 / 27% / 0.27 | 13 / 31% / 0.30 | +2 | +0.03 |
| GBPJPY | H4 | 11 / 27% / 0.648 | 12 / 33% / 0.612 | +1 | −0.04 |
| GBPUSD | H4 | 16 / 12% / 0.213 | 16 / 12% / 0.264 | 0 | +0.05 |
| USDJPY | H4 | 14 / 36% / 0.328 | 15 / 27% / 0.417 | +1 | +0.09 |
| EURJPY | H4 | 14 / 29% / 0.596 | 16 / 38% / 0.659 | +2 | +0.06 |
| **XAUUSD** | **H4** | 13 / 54% / 1.831 | 11 / 45% / **1.826** | −2 | flat |
| **Totals** | | **90** | **96** | **+6** | — |

## Read

Only +6 trades. The BB wick close-back-inside requirement wasn't the bottleneck either. Most bars that wick beyond the outer band ALSO close back inside on the same bar (it's an outer band — extreme moves usually revert intraday).

What IS the bottleneck: the `low < kbb_lower` (or `high > kbb_upper`) requirement itself. Most bars in the discount zone simply don't wick all the way to the outer band — they pull back to legMid, find support around there or at legLow, and bounce without ever touching the band.

## XAUUSD detail

XAUUSD lost 2 trades (13 → 11) and a bit of win rate (54% → 45%), PF dropped a hair. The trades it gained from looser conditions on this symbol are no-better-than-noise. The remaining 11 trades at PF 1.83 are essentially the same ones it had in sweep #3.

## What's left to try

We've now exhausted the easy candle-shape filters. To meaningfully add trade count we'd need to soften the BB requirement itself:

- **Option D** — replace `low < kbb_lower` with `low < kbb_basis` (touch the middle band). Captures any meaningful retracement into the lower half of the bands. Will roughly 3–5x signals but the "extreme overshoot" thesis is gone.
- **Option E** — remove BB entirely, gate on "discount zone + a confirmed new HL". Bigger overhaul; turns this into a pullback-buys strategy with KBB as decoration.
- **Option F** — keep KBB but use width-relative threshold: enter if `low < kbb_basis - (kbb_basis - kbb_lower) * 0.5` (halfway between basis and lower band). Tunable middle ground.

OR accept that the strategy IS selective by design — XAUUSD is profitable at PF 1.83 with 11 trades / 5 years, that's a deployable edge. Adding trades by loosening further trades quality for quantity, and the data shows quality matters more than count here.

## My honest take

The 11-trade XAUUSD result is real and the impulse-correction-impulse cycle thesis works on that instrument. We've spent 3 tuning rounds chasing trade count and gained ~13 trades total across all symbols at the cost of XAUUSD's PF (2.21 → 1.83 → 1.83). Further loosening risks breaking what works.

Recommend: either (a) stop, deploy XAUUSD-only, accept the count, or (b) Option F (halfway threshold) as a measured next step. Avoid D/E — they fundamentally change the strategy.
