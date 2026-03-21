# Simple SMC Trend Strategy

## Overview

A trend-following strategy that combines Smart Money Concepts (SMC) structural trend on H4 with RSI momentum entries on H1. Trades in the direction of the higher-timeframe trend when price reaches oversold/overbought levels on the lower timeframe.

**Playbook IDs:**
- v1: Playbook #4 (`simple_smc_trend.json`)
- v2: Playbook #5 (`smc_trend_v2.json`) — improved version

**Symbols:** XAUUSD, EURUSD, GBPJPY
**Primary Timeframe:** H1
**Structure Timeframe:** H4

---

## Strategy Logic

### Entry — Long (BUY)

```
1. H4 SMC trend is bullish (trend == 1)
   → Higher-timeframe structure confirms uptrend (HH + HL pattern)

2. H4 ADX > 18 (v2 only)
   → Market is trending, not ranging — filters out choppy conditions

3. H1 RSI crosses below threshold (v1: 35, v2: 32)
   → Price is oversold on the lower timeframe — pullback in an uptrend

4. Previous bar RSI was above threshold
   → Confirms the cross just happened (entry trigger, not persistent state)
```

**Action:** Open BUY with ATR-based SL and TP

### Entry — Short (SELL)

```
1. H4 SMC trend is bearish (trend == -1)
2. H4 ADX > 18 (v2 only)
3. H1 RSI crosses above threshold (v1: 65, v2: 68)
4. Previous bar RSI was below threshold
```

**Action:** Open SELL with ATR-based SL and TP

### Stop Loss & Take Profit

| Parameter | v1 | v2 |
|-----------|----|----|
| Stop Loss | 2.0× H1 ATR | 2.5× H1 ATR |
| TP (v1) / TP2 (v2) | 3.0× H1 ATR | 4.0× H1 ATR |
| TP1 (partial) | — | 2.0× H1 ATR |

### Position Management (v2)

| Rule | Trigger | Action | Once? |
|------|---------|--------|-------|
| Breakeven | Price reaches 1.5R profit | Move SL to entry + 0.3 ATR | Yes |
| Partial Close | Price reaches TP1 (2R) | Close 50% of position | Yes |
| Trailing Stop | Price reaches 2.5R profit | Trail SL at 1.5 ATR distance | No (continuous) |
| Trend Reversal Exit | H4 trend flips direction | Close entire position | — |
| Timeout | 60 H1 bars (~2.5 days) | Return to scanning | — |

---

## Phase Flow

```
                    ┌──────────────────────┐
                    │      SCANNING        │
                    │  evaluate_on: [H1]   │
                    │                      │
                    │  Wait for:           │
                    │  - H4 bullish/bearish│
                    │  - ADX > 18 (v2)     │
                    │  - RSI cross extreme  │
                    └──────┬──────┬────────┘
                           │      │
              RSI < 32 +   │      │  RSI > 68 +
              H4 bullish   │      │  H4 bearish
                           ▼      ▼
              ┌────────────┐      ┌─────────────┐
              │  IN_LONG   │      │  IN_SHORT   │
              │            │      │             │
              │ Breakeven  │      │ Breakeven   │
              │ Partial 50%│      │ Partial 50% │
              │ Trail stop │      │ Trail stop  │
              │ Trend exit │      │ Trend exit  │
              │ 60-bar TO  │      │ 60-bar TO   │
              └──────┬─────┘      └──────┬──────┘
                     │                   │
                     │  trade closed     │
                     └───────┬───────────┘
                             │
                             ▼
                     back to SCANNING
```

---

## Indicators Used

| ID | Indicator | Timeframe | Purpose |
|----|-----------|-----------|---------|
| `h4_smc` | SMC_Structure | H4 | Trend direction (bullish/bearish) |
| `h1_rsi` | RSI (14) | H1 | Entry trigger (oversold/overbought cross) |
| `h1_atr` | ATR (14) | H1 | SL/TP sizing |
| `h4_adx` | ADX (14) | H4 | Trend strength filter (v2 only) |
| `h1_nwe` | NW_Envelope | H1 | Available for refinement (not used in conditions) |
| `h1_kernel_ao` | Kernel_AO | H1 | Available for refinement (not used in conditions) |

---

## Backtest Results

### v1 (H1, 5000 bars per symbol)

| Symbol | Trades | Win Rate | PnL | Sharpe | Profit Factor | Max DD |
|--------|--------|----------|-----|--------|---------------|--------|
| XAUUSD | 64 | 65.6% | $7,759 | 3.77 | 2.05 | 14.7% |
| EURUSD | 69 | 59.4% | $284 | 2.18 | 1.37 | — |
| GBPJPY | 102 | 50.0% | -$38 | -0.06 | 0.99 | — |

**v1 Issues:**
- SL too tight (2× ATR) — 56-70% of trades hit SL
- No trend strength filter — trades in ranging markets
- RSI thresholds too loose (35/65) — too many weak signals
- GBPJPY shorts particularly poor (46% WR, -$15.78 avg)

### v2 (H1, 5000 bars per symbol)

| Symbol | Trades | Win Rate | PnL | Sharpe | Profit Factor | Max DD |
|--------|--------|----------|-----|--------|---------------|--------|
| XAUUSD | 36 | 72.2% | $5,894 | 5.59 | 3.07 | 11.8% |
| EURUSD | 32 | 68.8% | $77 | 1.30 | 1.24 | 1.1% |
| GBPJPY | 58 | 69.0% | $1,174 | 3.06 | 1.63 | 3.6% |

### v1 → v2 Improvement Summary

| Metric | XAUUSD | EURUSD | GBPJPY |
|--------|--------|--------|--------|
| Win Rate | +6.6pp | +9.4pp | **+19.0pp** |
| Sharpe | +1.82 | -0.88 | **+3.12** |
| Profit Factor | +1.02 | -0.13 | **+0.64** |
| Trade Count | -44% | -54% | -43% |

**Key finding:** ADX filter was the single biggest improvement — eliminated ranging market trades that were the primary source of losses, especially on GBPJPY.

---

## Improvement Ideas (Not Yet Implemented)

1. **Add NW Envelope zone filter** — only buy near lower NWE band, sell near upper band
2. **Add Kernel AO momentum confirmation** — require momentum aligned before entry
3. **Use SMC strong levels for SL** — place SL behind H4 strong low/high instead of arbitrary ATR
4. **Time-of-day filter** — avoid Asian session entries (lower volatility)
5. **Dynamic RSI thresholds** — adjust based on recent volatility (wider in volatile markets)
6. **Per-symbol optimization** — different RSI/ADX thresholds per symbol

---

## Other Strategies

### Strategy Portfolio Summary

All strategies run on H1 primary timeframe with H4 structural filter.

**Trend-Following (trade WITH the H4 trend):**

1. **Simple SMC Trend v2** (Playbook #5) — Best all-rounder
   - Logic: H4 bullish + ADX>18 + RSI crosses below 32 → BUY (mirror for SELL)
   - Indicators: H4 SMC, H4 ADX, H1 RSI, H1 ATR
   - Position mgmt: breakeven 1.5R, partial 50% at 2R, trail 1.5 ATR after 2.5R
   - Results: XAUUSD 72.2% WR $5,894 Sharpe 5.59 | EURUSD 68.8% WR $77 | GBPJPY 69.0% WR $1,174

2. **Trend Continuation v2** (Playbook #6) — Best risk-adjusted
   - Logic: H4 trend + ADX>20 → capture equilibrium → wait for pullback below equilibrium + RSI bounce + MACD confirm → BUY
   - Indicators: H4 SMC, H4 ADX, H1 RSI, H1 ATR, H1 Bollinger, H1 MACD
   - Two-phase: stores equilibrium level as variable, then uses it as pullback target
   - Results: XAUUSD 75.0% WR $2,711 Sharpe 6.61 | GBPJPY 100% WR $563 Sharpe 22.59

**Reversal (trade AGAINST the trend):**

3. **SMC Reversal v2** (Playbook #7) — Moderate
   - Logic: Track H4 trend in variable, detect flips (prev_trend != current trend) → wait for RSI low zone + Stoch K>D → enter in new direction
   - Indicators: H4 SMC, H4 ADX, H1 RSI, H1 ATR, H1 MACD, H1 Stochastic
   - Results: XAUUSD 53.3% WR $748 Sharpe 3.20 PF 1.74 (20K bars) | EURUSD 50% break-even

4. **Divergence Reversal v2** (Playbook #8) — Situational
   - Logic: RSI deeply extreme (<28/>72) + Stochastic K/D cross + MACD momentum shift → counter-trend entry
   - Indicators: H4 SMC, H1 RSI, H1 ATR, H1 Stochastic, H1 MACD, H1 Bollinger
   - Results: EURUSD 72.7% WR $30 PF 1.10 (works on ranging pairs) | XAUUSD -$2,108 (fails on gold trends)

### Timeframe Comparison (all strategies tested on H4, H1, M15)

| Primary TF | Result |
|---|---|
| H4 | Too slow — RSI fires on same TF as structure filter. 40-57% WR. |
| **H1** | **Sweet spot** — catches meaningful pullbacks. 65-100% WR. |
| M15 | Too noisy — RSI bounces too frequently. 28-44% WR (except Trend Cont v2). |

### Key Lessons Learned

1. ADX filter was the single biggest improvement — removed ranging market trades
2. Event flags (BOS/CHoCH/divergence) don't work as entry conditions — they fire for one bar only
3. Two-phase approach (capture state in variables → use in next phase) solves the event flag problem
4. Trend-following dominates reversal — 65-75% WR vs 45-53% WR
5. Gold trends too strongly for counter-trend strategies
6. Wider SL (2.5x ATR vs 2x) reduces premature stop-outs
