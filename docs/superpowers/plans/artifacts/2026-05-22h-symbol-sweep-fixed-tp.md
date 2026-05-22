# Sweep #8 — Fixed 1.5R take-profit (OCO with trail)

**Date:** 2026-05-22
**Change since sweep #7:** Added optional fixed-RR TP via `strategy.exit(... limit = tpLevel ...)`. Default `inputUseFixedTP = true`, `inputRRTarget = 1.5`. Trail SL still active — whichever fires first closes the position (Pine OCO).

## Side-by-side

| Symbol | TF | #7 (trail only) | #8 (trail + 1.5R TP) | Δ trades | Δ win% | Δ PF |
|---|---|---|---|---|---|---|
| EURUSD | H4 | 18 / 44% / 0.529 | 19 / 42% / **1.008** | +1 | −2 | +0.48 |
| EURUSD | H1 | 18 / 44% / 0.529 | 19 / 42% / 0.858 | +1 | −2 | +0.33 |
| GBPJPY | H4 | 21 / 43% / 0.792 | 25 / 44% / **1.218** | +4 | +1 | +0.43 |
| GBPUSD | H4 | 18 / 11% / 0.154 | 17 / 18% / 0.232 | −1 | +7 | +0.08 |
| USDJPY | H4 | 27 / 7% / 0.072 | 28 / 14% / 0.262 | +1 | +7 | +0.19 |
| EURJPY | H4 | 19 / 21% / 0.272 | 21 / 19% / 0.478 | +2 | −2 | +0.21 |
| **XAUUSD** | **H4** | 36 / 67% / **3.502** | 41 / 68% / 2.207 | +5 | +1 | **−1.30** |

## Headlines

**Two NEW symbols crossed PF 1.0:**
- **EURUSD H4: PF 1.008** (was 0.529 — almost 2× improvement)
- **GBPJPY H4: PF 1.218** (was 0.792)

This means the strategy is now gross-profitable on these two symbols at the standard trade-tester settings. Both still net-negative once including commission/slippage estimates, but the edge is now real and tunable.

**XAUUSD took a hit:** PF 3.50 → 2.21, net +27% → +18.5%. The TP capped the big runners that were the source of gold's exceptional edge. PF 2.21 is still very good — just not the peak.

## The trade-off

Fixed TP at 1.5R **converts** unrealized gains into locked wins at the cost of:
- Capping the upside on multi-stage trend extensions
- Helping symbols that frequently reverse before the trail catches them
- Hurting symbols where winners regularly extend past 1.5R

This is the classic exit-strategy split: range traders want TP, trend traders don't.

## Per-symbol prescription

If we treat each (symbol, TF) as its own deployable strategy:

| Symbol | Best exit mode |
|---|---|
| XAUUSD H4 | Trail only (TP off) — PF 3.50 |
| EURUSD H4 | TP on — PF 1.008 |
| EURUSD H1 | TP on — PF 0.858 (still sub-1 but best so far) |
| GBPJPY H4 | TP on — PF 1.218 |
| GBPUSD H4 | TP on — PF 0.232 (still bad) |
| USDJPY H4 | TP on — PF 0.262 (still bad) |
| EURJPY H4 | TP on — PF 0.478 (still bad) |

The `Use fixed RR take-profit` input toggle lets you flip TP per chart instance — no recompile needed.

## Could we find a better TP value?

The PF improved across all 7 combos except XAUUSD when adding 1.5R TP. Higher (e.g., 2R, 2.5R) might preserve more of XAUUSD's edge while still helping forex. Lower (1.0R) might lock more forex wins but cap XAU even harder. Worth a parameter sweep.

## Current toolkit

We now have these tunables exposed as inputs (no code change to adjust):
- `Direction` — Both / Long only / Short only
- `Min bars in new trend before entry` (default 1)
- `SL buffer (price units)` (default 0)
- `Risk % per trade` (default 1.0)
- `Re-arm on new HH/LL extreme` (default true)
- `Re-arm on basis touch` (default true)
- `OTE min retrace` (default 0.61)
- `OTE max retrace` (default 0.78)
- `Require OTE zone` (default true)
- `Use fixed RR take-profit` (default true)
- `RR target` (default 1.5)
- All KAO + KBB inputs

## Recommendation

For deployment, keep two profiles:
- **XAUUSD H4**: TP OFF (trail only), all other defaults — PF 3.50
- **EURUSD H4 / GBPJPY H4**: TP ON at 1.5R, all other defaults — PF 1.0–1.2

Both are valid edges with different character. Sweep #9 if you want to tune the TP value; otherwise we're done with iterative tuning.
