# Strategy Version Index

Every meaningful config milestone is preserved as a git tag. To retrieve any version's Pine source:

```bash
cd D:/trade-agent
git show v05-ote-on:pinescript/smc-kao-resumption-strategy.pine > /tmp/v05.pine
```

Or to restore that version as the working file (overwrites current):

```bash
cd D:/trade-agent
git checkout v05-ote-on -- pinescript/smc-kao-resumption-strategy.pine
```

After restoring, paste into TradingView's Pine editor.

## Milestones

| Tag | Commit | What it is | Backtest headline |
|---|---|---|---|
| `v01-initial-build` | `6f6dfdd` | Full initial build: KAO + KBB + state machine + entries + exits + sizing + alerts + visual layer. CHoCH-only legs, single entry per trend, KBB-wick trigger only. | EURUSD H4 11/36%/PF 0.611 / XAUUSD H4 4/25%/PF 0.062 |
| `v02-anchor-fix` | `3f798d6` | Impulse leg anchored on prior confirmed swing (`pl`/`ph`) instead of CHoCH bar. Still CHoCH-only legs. | XAUUSD H4 16/56%/PF 1.79 — first time XAU lifted |
| `v03-per-bos-legs` | `f518563` | Each BoS resets the sub-impulse leg (per-BoS model). `minBars` default 1. | XAUUSD H4 11/55%/PF 2.21 — sweep #3 breakthrough |
| `v04-pyramiding-5` | `ec9537f` | Pyramiding raised from 1 to 5; re-arm fires during open positions. | XAUUSD H4 51/57%/PF 2.40 / +34% net — sweep #6 |
| `v05-ote-on` | `2046f50` | OTE 61–78% retracement filter added (toggleable). | XAUUSD H4 36/67%/PF 3.50 — sweep #7 |
| `v06-fixed-rr-tp` | `5f76995` | Optional fixed-RR TP added (default 1.5R). | EURUSD H4 19/42%/PF 1.01 — first forex above PF 1 — sweep #8 |
| `v07-kbb-or-fvg-peak` | `a283573` | TP off + breakeven off + KBB-or-FVG default. The "15-trade peak". | XAUUSD H4 15/67%/PF 5.64 (note: see PF correction below) |
| `v08-fvg-gated-bos` | `b2ee20a` | BoS leg-reset gated by FVG-presence (≥1 FVG in BoS leg required). | XAUUSD H1 46/72%/PF 5.88 (note: PF likely ~1.92 — see below) |
| `v09-15-trade-restore` | `6bf0bcd` | Restored the v07 config for full 7-symbol sweep. | XAUUSD H4 17/65%/PF 3.79 |
| `v10-fvg-kernel-current` | `7875e21` | Current HEAD. Adds `FVG + Kernel` entry trigger, in-leg FVG scope, fixed-lot sizing option, 2-pip commission, 100x leverage. Default 0.1 XAU lot. | (in testing) |

## PF reading correction

The user flagged on 2026-05-25 that I had misread PF values across multiple sweeps — leading digit "1" mistaken for "5" in screenshots. The corrected XAUUSD H1 baseline (v08) is **PF 1.923, not 5.88**. Earlier headline numbers (PF 3.50, 5.64, 5.88) all likely shift down to 1.50, 1.64, 1.92 respectively.

The strategy is still a genuine positive edge — just more modest than the original headlines suggested. Annualized return on $10K at 1% risk: ~5–7%/year with ~4–6% max drawdown.

## How to use this

1. Pick a version from the table.
2. Run `git show <tag>:pinescript/smc-kao-resumption-strategy.pine` to inspect or extract.
3. To deploy a specific version: `git checkout <tag> -- pinescript/smc-kao-resumption-strategy.pine`, then re-paste into TV.
4. To get back to current: `git checkout master -- pinescript/smc-kao-resumption-strategy.pine`.

## Detail per sweep

Each sweep has its own artifact markdown in this directory:
- `2026-05-21-symbol-sweep.md` — sweep #1 (initial baseline)
- `2026-05-22b-symbol-sweep-after-anchor-fix.md` — sweep #2
- `2026-05-22c-symbol-sweep-after-per-bos-legs.md` — sweep #3
- `2026-05-22d-symbol-sweep-after-body-filter.md` — sweep #4
- `2026-05-22e-symbol-sweep-after-close-inside-dropped.md` — sweep #5
- `2026-05-22f-symbol-sweep-pyramiding-5.md` — sweep #6
- `2026-05-22g-symbol-sweep-ote-zone.md` — sweep #7
- `2026-05-22h-symbol-sweep-fixed-tp.md` — sweep #8
- `2026-05-22i-symbol-sweep-structural-tp-breakeven.md` — sweep #9
- `2026-05-23-symbol-sweep-fvg-trail-only.md` — sweep #11
- `2026-05-23b-symbol-sweep-fvg-gated-bos.md` — sweep #12

Each contains the full per-symbol metrics table and a "what changed" narrative.

## All commits affecting the strategy

Run `git log --oneline --follow pinescript/smc-kao-resumption-strategy.pine` to see every single change.
