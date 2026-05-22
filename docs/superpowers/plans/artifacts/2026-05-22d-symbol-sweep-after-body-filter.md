# Sweep #4 — After dropping body-color filter

**Date:** 2026-05-22
**Change since sweep #3:** Removed `close > open` (long) and `close < open` (short) from entry conditions. Wick rejection (low/high beyond outer band + close back inside) remains; bullish/bearish body no longer required.

## Side-by-side vs sweep #3

| Symbol | TF | #3 (per-BoS) | #4 (body filter off) | Δ trades | Δ PF |
|---|---|---|---|---|---|
| EURUSD | H4 | 10 / 30% / 0.31 | 11 / 27% / 0.27 | +1 | −0.04 |
| EURUSD | H1 | 10 / 30% / 0.30 | 11 / 27% / 0.27 | +1 | −0.03 |
| GBPJPY | H4 | 10 / 30% / 0.739 | 11 / 27% / 0.648 | +1 | −0.09 |
| GBPUSD | H4 | 16 / 12% / 0.214 | 16 / 12% / 0.213 | 0 | flat |
| USDJPY | H4 | 13 / 15% / 0.254 | 14 / 36% / 0.328 | +1 | +0.07 |
| EURJPY | H4 | 13 / 31% / 0.629 | 14 / 29% / 0.596 | +1 | −0.03 |
| XAUUSD | H4 | 11 / 55% / 2.212 | 13 / 54% / **1.831** | +2 | −0.38 |
| **Totals** | — | **83 trades** | **90 trades** | **+7** | — |

## Read

The body filter wasn't the bottleneck. +7 trades across 7 combos (~8% increase) is trivial — most setups that fired with the wick rejection ALSO happened to be bullish/bearish candles, so dropping that filter barely changed anything.

**XAUUSD H4 stayed profitable** at PF 1.83 (down from 2.21 but still strongly positive, and on +2 more trades).

## The actual bottleneck

The remaining trigger requires `low < kbb_lower AND close > kbb_lower` on the same bar — a specific candle shape (long lower wick that closes back inside the band). This is rare. To meaningfully add signals, we'd have to soften this:

- **Option A** — drop `close > kbb_lower`: any bar that wicks beyond the band qualifies, regardless of where it closes. Captures all extreme-overshoot bars including ones that close beyond the band (continuation breakouts). Probably +200-300% signals but lower quality.
- **Option B** — split into two-bar pattern: bar N wicks beyond band, bar N+1 closes back inside band → enter on N+1. Captures rejections that take an extra bar to confirm. Moderate signal increase, preserves quality.
- **Option C** — drop the BB requirement entirely; enter purely on "in discount zone + new HL forms". The BB becomes a filter applied only for sizing/confidence, not gating. Largest signal increase, fundamentally different strategy.

## Recommendation

**Option B** (two-bar rejection pattern) is the cleanest principled add — it keeps the "correction exhaustion" thesis but doesn't demand the rejection happen entirely within one bar. Expected ~50% more signals than current, similar PF or better.

**Option A** is more aggressive and likely loses XAUUSD's edge by including continuation breakouts (which we explicitly didn't want to trade).

Want B?
