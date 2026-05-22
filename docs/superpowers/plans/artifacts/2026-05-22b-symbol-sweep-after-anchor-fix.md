# Sweep #2 — After impulse-leg anchor fix

**Date:** 2026-05-22 (post fix commit `3f798d6`)
**Change:** legLow on bull CHoCH now anchors at `lastConfirmedLow` (prior `pl` from KAO); legHigh on bear CHoCH at `lastConfirmedHigh` (prior `ph`).
**Inputs:** all defaults (same as sweep #1).

## Side-by-side: pre-fix vs post-fix

| Symbol | TF | Before | After | Δ trades | Δ win% | Δ PF | Verdict |
|---|---|---|---|---|---|---|---|
| EURUSD | H4 | 11 / 36% / 0.611 | 10 / 40% / 0.476 | −1 | +4 | −0.135 | slight regression |
| EURUSD | H1 | 9 / 44% / 0.457 | 10 / 40% / 0.478 | +1 | −4 | +0.021 | flat (tester used 3yr range this run) |
| GBPJPY | H4 | 7 / 28% / 0.232 | 5 / 0% / 0.000 | −2 | −28 | −0.232 | regression (all losers) |
| GBPUSD | H4 | 18 / 11% / 0.048 | 17 / 18% / 0.232 | −1 | +7 | +0.184 | improvement |
| USDJPY | H4 | 11 / 36% / 0.505 | 10 / 30% / 0.706 | −1 | −6 | +0.201 | improvement |
| EURJPY | H4 | 11 / 27% / 0.242 | 14 / 36% / 0.737 | +3 | +9 | +0.495 | big improvement |
| XAUUSD | H4 | 15 / 13% / 1.140 | 4 / 25% / 0.062 | −11 | +12 | −1.078 | huge regression |

## Read

- **The fix does what it was designed to do** — anchoring the impulse origin at the prior swing means the discount zone is now correctly positioned in the lower half of the actual impulse range.
- **But the strategy still loses on every symbol.** No combo has PF > 1.
- **Mixed-direction outcomes by symbol** suggest the wick-rejection-while-in-discount entry trigger is fundamentally too rare AND too late on these instruments. Half the symbols got fewer entries (because price doesn't reach the deeper discount before the BB wick condition expires), half saw shuffled entries that performed worse on the picky symbols (GBPJPY, XAUUSD).
- **XAUUSD collapsed from 15 trades to 4.** Gold's swings are huge → prior pivots are far below → discount zone is very deep → almost no bars satisfy both `low < legMid` AND `low < kbb_lower`.

## Conclusion on impulse-leg model

The leg anchoring is now **correct per spec**. The strategy's continued under-performance is downstream — the *combination* of (deep discount + BB outer wick rejection + bullish body + min-bars-in-trend ≥ 5) is too restrictive on the asymmetric, fast-moving instruments tested.

## Tuning levers to try next (highest leverage first)

1. **Drop `inputMinBarsTrend` 5 → 1.** Allows entries on the very first valid setup after a CHoCH, which is when the impulse is most likely still alive.
2. **Soften the wick-rejection condition.** Currently requires `low < kbb_lower` AND `close > kbb_lower` AND `close > open` — three things on one bar. Try requiring just `low < kbb_lower` AND `close > kbb_lower` (drop the bullish-body filter), or expand to "wick OR close-back-inside on next bar".
3. **Try entering on `low <= legMid` (touch) instead of `low < legMid` (must dip past).** Captures shallow-but-valid retracements that just kiss the 50% level.
4. **Test "trail off" mode.** As before — the structural trail probably cuts winners that come from the post-discount second impulse.
5. **Multi-confirmation OR mode.** Allow entry when EITHER the wick rejection fires OR price simply trades into the discount zone with a bullish/bearish bar (no BB requirement). The KBB wick becomes a quality filter, not a hard gate.

Want me to apply (1) + (3) and re-sweep? Those are 1-line changes and should produce 30-50 trades per symbol — enough to actually evaluate edge.
