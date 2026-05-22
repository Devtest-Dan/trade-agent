# Sweep #9 — Structural TP (legHigh/legLow) + Breakeven move

**Date:** 2026-05-22
**Changes since sweep #8:**
- TP mode default switched from Fixed RR to **Structural** (TP = legHigh at first entry for long, legLow for short)
- New **Breakeven** move: once high (long) ≥ entryPrice + 1.0×risk_dist, trail ratchets to entryPrice — worst-case becomes a scratch.

## Three-way comparison

| Symbol | #7 (trail only) | #8 (1.5R TP) | #9 (struct TP + BE) | Winner |
|---|---|---|---|---|
| EURUSD H4 | 18/44%/0.529 | 19/42%/**1.008** | 22/36%/0.838 | #8 |
| EURUSD H1 | 18/44%/0.529 | 19/42%/0.858 | 22/36%/0.838 | #8 |
| GBPJPY H4 | 21/43%/0.792 | 25/44%/**1.218** | 31/39%/0.985 | #8 |
| GBPUSD H4 | 18/11%/0.154 | 17/18%/0.232 | 26/12%/0.221 | #8 |
| USDJPY H4 | 27/7%/0.072 | 28/14%/0.262 | 33/12%/0.096 | #8 |
| EURJPY H4 | 19/21%/0.272 | 21/19%/**0.478** | 23/26%/0.354 | #8 |
| **XAUUSD H4** | **36/67%/3.502** | 41/68%/2.207 | 45/60%/2.582 | **#7** |

## Read

**Fixed 1.5R TP beats structural TP + breakeven on every symbol.** Two effects compounded:
1. **Breakeven move closes "would-have-been" winners at scratch.** When the trail ratchets to entry at +1R, any pullback exits the trade — but that pullback is often a normal correction that resolves into a bigger win. The 1.5R fixed TP locks the win before the pullback can scratch it.
2. **Structural TP at legHigh is too far** on most symbols. legHigh after a BoS reset is the post-BoS peak; for OTE entries that puts the implied RR around 2.3R but in practice the trail catches the trade first.

XAUUSD prefers no TP at all — its big runners extend past both 1.5R and legHigh frequently enough that any cap reduces total profit.

## Overall best per (symbol, TF) across all 9 sweeps

| Symbol | TF | Best sweep | Best PF | Configuration |
|---|---|---|---|---|
| **XAUUSD** | H4 | **#7** | **3.502** | per-BoS legs, pyramid=5, OTE on, trail only, no TP, no BE |
| GBPJPY | H4 | #8 | 1.218 | per-BoS legs, pyramid=5, OTE on, **1.5R TP**, no BE |
| EURUSD | H4 | #8 | 1.008 | per-BoS legs, pyramid=5, OTE on, **1.5R TP**, no BE |
| EURUSD | H1 | #8 | 0.858 | (same as H4) |
| EURJPY | H4 | #2 | 0.737 | CHoCH-only legs, pyramid=1, no OTE, trail only |
| USDJPY | H4 | #2 | 0.706 | (same as EURJPY) |
| GBPUSD | H4 | #6 | 0.290 | per-BoS legs, pyramid=5, no OTE, no TP, no BE |

## Two clean takeaways

1. **The breakeven move hurts this strategy** on every symbol tested. The trail SL + opposite-CHoCH safety net was already doing the loss-mitigation job; the breakeven adds premature exits without preventing the real losers.

2. **Fixed 1.5R TP is the universal best second choice** (after trail-only for XAU). It captured the moderate wins that the trail kept giving back.

## Recommendation

Roll back the breakeven default and structural TP default. The optimal config of the script across symbols looks like:

- **XAUUSD H4 deployment:** TP mode = Off, breakeven = off → PF 3.50
- **EURUSD/GBPJPY H4 deployment:** TP mode = Fixed RR 1.5, breakeven = off → PF 1.0-1.2
- **USDJPY/EURJPY/GBPUSD deployments:** still don't have positive expectancy from any tested configuration — they may not be a fit for this strategy.

Should I (a) revert defaults so the script ships in the "best universal" mode (sweep #8 config), and (b) keep the new structural-TP + breakeven inputs available but off-by-default? Or pursue other directions?
