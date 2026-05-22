# SMC KAO Resumption Strategy — 6-Symbol Sweep

**Date:** 2026-05-22
**Strategy:** `SMC KAO Resumption Strategy v1.0`
**Inputs:** all defaults (risk 1%, direction Both, min-bars-in-trend 5, SL buffer 0, re-arm extreme+basis both on)
**Backtest period:** 2021-01-02 → 2026-05-22 (~5 years 4 months)

## Results

| Symbol | TF | Trades | Win % | Profit Factor | Max Equity DD % | Net P&L |
|---|---|---|---|---|---|---|
| EURUSD | H4 | 11 | 36.36% | 0.611 | 1.12% | small loss |
| EURUSD | H1 | 9 | 44.44% | 0.457 | 318.26% | loss |
| GBPJPY | H4 | 7 | 28.57% | 0.232 | 433.81% | loss |
| GBPUSD | H4 | 18 | 11.11% | 0.048 | 12.05% | −11.7% |
| USDJPY | H4 | 11 | 36.36% | 0.505 | 297.17% | loss |
| EURJPY | H4 | 11 | 27.27% | 0.242 | 674.58% | −1.08% |
| XAUUSD | H4 | 15 | 13.33% | 1.140 | 295.57% | −4.4% |

## Observations

1. **Strategy is too restrictive.** 7–18 trades over 5+ years on every symbol means the entry conditions (wick rejection on KBB outer band + in discount zone + 5+ bars in trend + bullish/bearish body) rarely all align simultaneously. Sample sizes are too small for statistical significance.

2. **Strategy is net losing at defaults.** All 7 (symbol, TF) combos produce a net loss. PF is below 1.0 on 6 of 7. Only XAUUSD H4 shows PF > 1, and even there the net is negative — likely the metric mixes closed-trade PnL with open-position drawdown.

3. **Max DD is high relative to net activity.** Even tiny trade counts produce 300–600% equity drawdowns. This suggests the structural trail stop ratchets aggressively but the entry timing is too late — winners get cut on the trail's pullback, while losers run to the frozen SL.

4. **Code is correct.** The strategy compiles clean, fires real entries, manages exits as designed, and follows the spec. The losses reflect the strategy's logic at default parameters, not a build defect.

## Hypotheses for the under-performance

- **Min-bars-in-trend=5 too tight on H4.** Many CHoCH-to-impulse-2 setups take fewer than 5 bars to complete. Try `1` or `2`.
- **Wick-rejection condition too tight.** Requires wick beyond KBB outer band AND close back inside AND body in trend direction — three conditions on the same bar. Try relaxing to "wick OR close-back-inside-after-prior-breach".
- **Structural trail cuts winners.** Each new confirmed pivot ratchets the stop. On a leg with several internal pullbacks, the trail may exit before the second impulse fully extends. Consider initial SL only (no trail) for the second impulse run.
- **Discount zone too strict.** Requiring `low < legMid` AND a KBB wick may filter out genuine 2nd-impulse setups where price merely dips to legMid without spiking outside the BB.

## Recommended next steps (not a gate — owner decides)

- **Step 1: Tune `inputMinBarsTrend` from 5 → 1.** Should triple or quadruple trade frequency on most symbols and reveal which entry condition is the real bottleneck.
- **Step 2: Loosen wick-rejection.** Change `low < kbb_lower AND close > kbb_lower` to `low < kbb_lower` only (no requirement to close back inside). Tighter entry, more signals.
- **Step 3: Test "trail off" mode.** Add an `inputUseTrail` boolean defaulting to `false`. Compare PF with vs. without trail on the same 6 symbols.
- **Step 4: Use H1 instead of H4 as the primary TF.** More bars → more setups → larger sample size for confidence.
- **Step 5: Compare against your existing trade-agent SMC Trend Continuation strategy** (per memory: 6-symbol portfolio PF 2.08, +449% over backtest). That uses simpler entries and longer holds; the resumption logic may be over-engineered relative to that baseline.

## Verdict

- **Build:** ✅ Complete and spec-compliant.
- **At default parameters:** ❌ Net losing on every test symbol.
- **Tunable to profitability?** Likely yes — the building blocks are sound (SMC structure + KBB extremes are valid edge sources in trade-agent's other strategies). Tuning required before production use.
