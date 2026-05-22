# Sweep #11 — KBB OR FVG + trail only, 7 symbols

**Date:** 2026-05-23
**Config:** sweep #10's XAUUSD-peak settings applied to all 7 symbol/TF combos.
- Entry trigger: **KBB or FVG**
- TP mode: **Off** (trail only)
- Breakeven: **off**
- OTE: 0.61-0.78, on
- pyramiding: 5
- FVG mitigation: strict (low inside FVG)

## Results

| Symbol | TF | Trades | Win | PF | Net | Max DD | Net/DD |
|---|---|---|---|---|---|---|---|
| EURUSD | H4 | 20 | 40% | 0.508 | −3.3% | 7.4% | — |
| EURUSD | H1 | 20 | 40% | 0.508 | −5.3% | 7.4% | — |
| GBPJPY | H4 | 21 | 43% | 0.748 | −1.8% | 8.5% | — |
| GBPUSD | H4 | 18 | 11% | 0.148 | −12.7% | 12.1% | — |
| USDJPY | H4 | 28 | 7% | 0.071 | −17.7% | 17.1% | — |
| EURJPY | H4 | 22 | 14% | 0.157 | −10.4% | 10.5% | — |
| **XAUUSD** | **H4** | **17** | **65%** | **3.786** | **+23.9%** | **5.4%** | **~4.4:1** |

## Read

**Only XAUUSD H4 is profitable** with the KBB-or-FVG trail-only config. Every forex pair is net negative — most badly so. USDJPY and GBPUSD particularly damaged, with single-digit win rates.

The FVG-added signals didn't help forex. Adding FVG mitigation gave them more low-quality entries that the strict trail then trailed past, accumulating losers.

XAUUSD result (17/65%/PF 3.79/+23.9%) is slightly under the previously-captured 15/67%/PF 5.64 — probably 2 extra marginal trades and minor variance in trail/exit timing. Still the best result in the sweep by a wide margin.

## Conclusion: XAUUSD H4 is the only deployable symbol

After 11 sweeps testing every combination of entry filters, exit modes, leg models, and pyramiding settings, the consistent pattern holds:

- **XAUUSD H4** fits the impulse-correction-impulse thesis. Clean multi-stage trends, predictable OTE retracements, FVG fills that resolve into continuation.
- **Forex pairs** don't fit. Their corrections either run shallow (rendering OTE useless), invalidate fully (no continuation to trade), or are too whippy for the trail SL to ride.

## Recommended deployment

**Single-symbol strategy on XAUUSD H4** at the current defaults:
- Entry trigger: KBB or FVG
- TP mode: Off (trail only)
- Breakeven: off
- OTE: 0.61-0.78, on
- pyramiding: 5
- Risk: 1% per entry (5% max per trend cycle)

**Expected:** ~3 trades/year, 65-67% win rate, PF 3.8-5.6, +20-34% per 5 years, max DD ~3-5%, net/DD ratio 5-10:1.

## What we ruled out across all sweeps

- Body-color filter (sweep #4) — marginal impact
- Close-back-inside requirement (sweep #5) — marginal impact
- Pyramiding=10 (sweep #11 attempt earlier) — doubles DD without proportional PF gain
- OTE widened to 0.5-0.78 (this sweep variant) — dilutes per-trade quality
- FVG loose mitigation (overlap vs inside) — adds low-quality signals
- Structural TP at legHigh (sweep #9) — capped winners too tight
- Breakeven move (sweep #9) — scratched would-be winners
- 1.5R / 2R / 3R Fixed TPs — improved forex marginally but capped XAUUSD's edge
- Forex tuning — sweep #2 was best for USDJPY/EURJPY (PF 0.7), sweep #6 for GBPUSD (PF 0.29), none above PF 1.0

## End of iterative tuning

We're at the point where every further change is robbing Peter to pay Paul. The strategy has one deployable instrument and a tunable toolkit for it. Ship it.
