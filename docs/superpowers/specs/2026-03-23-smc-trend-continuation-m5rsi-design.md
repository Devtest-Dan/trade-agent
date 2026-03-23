# SMC Trend Continuation — M5 RSI + Re-Entry Design Spec

**Symbols:** EURUSD, GBPJPY (lot 1.0) | XAUUSD longs only (lot 0.2)
**Date:** 2026-03-23
**Based on:** v7 with two key changes: M5 RSI Kernel + re-entry after trade close

## Overview

A trend-continuation playbook using H4 Smart Money Concepts for directional bias, M15 Nadaraya-Watson Envelope for pullback detection, M5 RSI Kernel for momentum entry trigger, and H1 MACD 4C as a momentum filter. After a trade closes, the strategy skips idle and goes straight back to scanning for the next pullback — catching multiple entries within the same trend.

## Indicators (5 total)

| ID | Indicator | Timeframe | Role |
|----|-----------|-----------|------|
| `h4_smc` | SMC_Structure v2.14 | H4 | Directional bias — trend direction, swing highs/lows (ref_low/ref_high for SL), OB/FVG zones (for TP), BOS/CHOCH signals |
| `m15_nwe` | NW_Envelope | M15 | Pullback detection — price reaching lower/upper near bands signals a pullback to value |
| `m5_rsi_kernel` | RSI_Kernel (period 7) | M5 | Momentum trigger — RSI crossing above/below its kernel smoothing line confirms momentum shift |
| `h1_macd4c` | MACD_4C (12/26) | H1 | Momentum filter — MACD must be rising for longs, falling for shorts |
| `h4_atr` | ATR (14) | H4 | SL/TP fallback sizing, breakeven threshold (1.5x), trailing activation (2x) |

### Key Parameters

| Parameter | Value |
|-----------|-------|
| NWE near_factor | 1.5 |
| NWE far_factor | 8.0 |
| NWE lookback_window | 8 |
| NWE atr_length | 60 |
| RSI length | 7 (short for reactivity) |
| RSI kernel_lookback | 8 |
| RSI kernel_weight | 8.0 |
| SMC swing_len | 10 |
| MACD fast/slow | 12/26 |
| ATR period | 14 |

## Phase Machine (7 phases)

```
idle ──┬── scanning_long ── entry_ready_long ── in_trade_long ──┐
       │                                            │            │
       │                                  (re-entry to scanning) │
       └── scanning_short ── entry_ready_short ── in_trade_short ┘
                                                     │
                                           (re-entry to scanning)
```

**Key difference from v7:** `on_trade_closed` goes to `scanning_long/short` instead of `idle`. This means after a trade closes, if the H4 trend is still valid, the strategy immediately looks for the next pullback without waiting for a new H4 bias check.

### Phase: `idle`
- **Evaluate on:** M15, H4
- **To `scanning_long`:** H4 SMC trend == bullish AND zone != premium
- **To `scanning_short`:** H4 SMC trend == bearish AND zone != discount

### Phase: `scanning_long`
- **Evaluate on:** M15, H4
- **To `entry_ready_long`:** price <= M15 NWE lower_near (pullback detected)
- **Back to `idle`:** H4 trend no longer bullish
- **Timeout:** 200 M15 bars (~3.3 days) → idle

### Phase: `entry_ready_long`
- **Evaluate on:** M5, M15, H4
- **To `in_trade_long`** (all AND):
  1. M5 RSI Kernel cross above == 1.0 (momentum trigger)
  2. H1 MACD rising == 1.0 (higher TF momentum agrees)
- **Actions on entry:**
  - SL = H4 SMC ref_low (swing low) if valid, else price - 2.5x H4 ATR
  - TP = H1 opposing FVG → opposing OB → price + 4x H4 ATR (conditional chain via nested iff)
  - Open BUY, lot from risk.max_lot
- **Back to `scanning_long`:** price > M15 NWE yhat (returned above midline)
- **Back to `idle`:** H4 trend flipped
- **Timeout:** 100 M15 bars (~25 hours) → scanning_long

### Phase: `in_trade_long`
- **Evaluate on:** M5, M15, H4
- **Position management:**
  1. **Breakeven** (once): pnl > 1.5x H4 ATR → SL to entry price
  2. **NWE trailing** (continuous): pnl > 2x H4 ATR AND M15 NWE lower_near > current SL → SL to lower_near
- **CHoCH exit:** H4 bearish CHOCH → close immediately
- **On trade closed:** → `scanning_long` (RE-ENTRY — not idle)
- **Timeout:** 500 M15 bars (~5.2 days) → idle

### Shorts: Exact mirror with inverted conditions

### XAUUSD variant
- Identical logic but **longs only** — short transitions removed from idle
- Lot: 0.2 (vs 1.0 for FX)

## Risk Configuration

| Parameter | FX Majors | XAUUSD |
|-----------|-----------|--------|
| max_lot | 1.0 | 0.2 |
| max_daily_trades | 3 | 3 |
| max_open_positions | 1 | 1 |
| max_drawdown_pct | 5.0 | 5.0 |

## Why M5 RSI Kernel (vs M15)

The M5 RSI Kernel catches momentum shifts ~3x earlier than M15. When price pulls back to the M15 NWE band and starts bouncing, the M5 RSI crosses its kernel within 1-2 M5 bars, while M15 RSI waits for the full 15-min candle to close. This results in:
- Tighter entries (better fill price)
- Smaller average loss ($131 vs $208)
- Higher win/loss ratio (2.77 vs 1.92)
- Lower drawdown (9.1% vs 15.1%)

## Why Re-Entry

Without re-entry, after every trade the strategy goes back to `idle` and waits for the next H4 bar to confirm the trend again. In a strong trend, this means missing 2-4 additional pullback entries. With re-entry:
- XAUUSD went from 8 to 30 trades in v7 (same trend, multiple pullbacks)
- Total portfolio trades increased 67% (v7 M15)
- The scanning phase still checks if the trend is valid — if it flipped, it sends back to idle

## Portfolio Backtest Results ($10k shared account, M5 RSI + re-entry)

| Symbol | Lot | Trades | WR | PF | PnL |
|--------|-----|--------|-----|-----|------|
| EURUSD | 1.0 | 52 | 61.5% | 3.16 | +$3,645 |
| GBPJPY | 1.0 | 48 | 52.1% | 3.22 | +$10,795 |
| XAUUSD | 0.2 | 8 | 50.0% | high | +$1,606 |
| **Combined** | | **108** | **56.5%** | **3.60** | **+$16,046** |

| Metric | Value |
|--------|-------|
| Starting Balance | $10,000 |
| Ending Balance | $26,046 |
| Return | +160.5% |
| Max Drawdown | $1,128 (9.1%) |
| Recovery Factor | 14.23 |
| Expectancy/Trade | $148.57 |
| Avg Win / Avg Loss | $364 / $131 (2.77:1) |
| Max Consec Wins | 8 |
| Max Consec Losses | 6 |
| Profitable Months | 13/19 (68%) |
| Worst Month | -$292 (-2.9%) |
| Avg Monthly | +$845 (+8.4%) |

## Optimization History

### What was built (v1 → Final)

| Version | Key Change | Trades | PF | PnL | Max DD |
|---------|-----------|--------|-----|------|--------|
| v1 | Original: strict zone, RSI 14, SL 2x ATR | 46 | 0.50 | -$155 | 1.6% |
| v3 | + MACD 4C filter | 7 | 2.01 | +$29 | 0.3% |
| v5 | RSI period 7 + swing low SL | 32 | 2.00 | +$1,894 | 7.3% |
| v7 | Zone != opposite (neutral OK) | 48 | 2.27 | +$3,100 | 6.2% |
| v7+re | + Re-entry (on_trade_closed → scanning) | 167* | 2.09 | +$18,081* | 15.1% |
| **M5+re** | **M5 RSI Kernel + re-entry (FINAL)** | **108*** | **3.60** | **+$16,046*** | **9.1%** |

*Portfolio totals (3 symbols)

### What was tested and rejected (16 experiments post-v7)

| # | Modification | Result | Why It Failed |
|---|-------------|--------|---------------|
| 1 | ADX > 20 filter | -29% PnL | Cut good trades, SMC+MACD already handles regime |
| 2 | H1 NWE wide trailing at 3x ATR | -12% PnL | Wider bands gave back profits |
| 3 | RSI oversold/overbought entry filter | 2 trades | Too restrictive with other conditions |
| 4 | Kernel AO confluence | -67% PnL | Redundant with MACD |
| 5 | H1 NW Kernel replacing MACD | 37% WR, 1.33 PF | Slower than MACD rising/falling |
| 6 | H4 NW Kernel as bias | 19 trades | Too selective |
| 7 | M15 NW Kernel at entry | 15 trades | Contradicts pullback (kernel bearish at lower band) |
| 8 | M15 NW Kernel smooth crossover | 0 trades | Crossover too rare with other AND conditions |
| 9 | NWE yhat as pullback level | 913 trades, 0.97 PF | Way too easy to trigger |
| 10 | Session filter 07-20 UTC | -62% PnL | Strategy works all hours |
| 11 | Session filter skip 0-5 UTC | -45% PnL | Same — no session weakness |
| 12 | Pure H1 trend (shift all TFs down) | 370 trades, 0.49 PF | H1 SMC too noisy for bias |
| 13 | Partial close 50% at 1x ATR | +$344 (vs +$16k) | Kills big winners |
| 14 | Partial close 25% at 1x ATR | +$1,003 | Still caps runners |
| 15 | Partial close 25% at 3x ATR | +$1,629 | Better but -90% vs baseline |

### Key Learnings

1. **Don't stack filters on an already-filtered strategy** — each added filter has diminishing returns
2. **Partial close kills trend-following** — the edge is in winner size (2.77:1), not win rate
3. **NW Kernel is redundant with NWE** — the envelope already uses kernel regression internally
4. **Session filters hurt when the edge is structural** — SMC/NWE/RSI work 24/5
5. **Trend TF must be 4x+ the entry TF** — H1 trend is too noisy, H4 is stable
6. **MACD rising/falling > Kernel is_bullish** for momentum filtering — faster, more reactive
7. **M15 NWE trailing is optimal** — tighter than H1, wide enough to not choke runners
8. **Re-entry is the best way to increase trades** — no new filters, just smarter state machine flow

## Files

- FX playbook: `data/playbooks/smc_trend_continuation_m5rsi_fx.json` (Playbook ID 14)
- XAUUSD playbook: `data/playbooks/smc_trend_continuation_m5rsi_xauusd.json` (Playbook ID 15)
- Portfolio script: `scripts/portfolio_backtest.py`
- M5 bars: Built from M1 data (373k EURUSD, 84k GBPJPY, 354k XAUUSD)
- Memory: `smc-trend-continuation.md` (full learnings)
