# OB_FVG — Order Blocks & Fair Value Gaps

## 1. Overview

The OB_FVG indicator identifies institutional order blocks (supply/demand zones where large players entered), fair value gaps (imbalances in price delivery), breaker blocks (failed order blocks that flip polarity), and multi-layer ZigZag confluence. It provides precise entry zones when combined with structural bias from SMC_Structure.

**Indicator ID pattern:** `<timeframe>_ob_fvg` (e.g., `h4_ob_fvg`, `m15_ob_fvg`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `ob_upper` | float | Upper boundary of the nearest active order block |
| `ob_lower` | float | Lower boundary of the nearest active order block |
| `ob_type` | int | `1` = bullish OB, `-1` = bearish OB, `2` = breaker resistance (failed bull OB), `-2` = breaker support (failed bear OB) |
| `fvg_upper` | float | Upper boundary of the nearest unfilled FVG |
| `fvg_lower` | float | Lower boundary of the nearest unfilled FVG |
| `fvg_filled` | int | `0` = gap still open (untouched), `1` = gap has been filled/mitigated |
| `fvg_type` | int | `1` = bullish FVG (gap up), `-1` = bearish FVG (gap down) |
| `zz1_up` | float | ZigZag layer 1 — nearest swing high |
| `zz1_down` | float | ZigZag layer 1 — nearest swing low |
| `zz2_up` | float | ZigZag layer 2 — medium-term swing high |
| `zz2_down` | float | ZigZag layer 2 — medium-term swing low |
| `zz3_up` | float | ZigZag layer 3 — major swing high |
| `zz3_down` | float | ZigZag layer 3 — major swing low |
| `combined_all` | int | `1` if OB + FVG + ZigZag all align at current price, else `0` |
| `combined_partial` | int | `1` if at least 2 of 3 (OB, FVG, ZigZag) align, else `0` |

## 2. When to Use

- **Precision entries** — after SMC_Structure provides directional bias, use OB/FVG for exact entry price.
- **Supply/demand zone trading** — identify where institutional orders likely sit.
- **Gap trading** — FVGs represent inefficiency; price tends to return and fill them.
- **Confluence scoring** — `combined_all` and `combined_partial` give quick high-probability zone detection.
- **Breaker block reversals** — when a known OB fails, it becomes a breaker and flips to the opposite role.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `ob_lookback` | 20 | 10–100 | How many bars back to search for order blocks |
| `ob_strength` | 3 | 1–10 | Minimum candle body size (as ATR multiple * 0.1) to qualify as OB. Higher = stricter. |
| `fvg_min_size` | 0.5 | 0.1–3.0 | Minimum FVG size as ATR multiple. Filters tiny gaps. |
| `fvg_max_age` | 50 | 10–200 | Maximum bars an FVG remains active before expiring |
| `zz_depths` | [5, 13, 34] | varies | Lookback depths for the 3 ZigZag layers |
| `mitigation_threshold` | 0.5 | 0.0–1.0 | How much of the OB zone price must penetrate to consider it mitigated (0.5 = 50%) |

**XAUUSD recommended:** `ob_strength: 4`, `fvg_min_size: 0.8` (gold has large candles; filter small zones that get swept easily).

## 4. Key Patterns & Setups

### 4.1 Bullish Order Block Entry

Price returns to a bullish OB zone after a BOS. The OB acts as demand — expect price to bounce.

**Enter long when price reaches bullish OB:**
```json
{
  "phase": "wait_for_ob_entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure (from SMC)"},
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "1", "description": "Bullish order block detected"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price entered OB zone"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price above OB lower boundary"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.2 Bearish Order Block Entry

**Enter short when price reaches bearish OB in bearish structure:**
```json
{
  "phase": "wait_for_ob_sell",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Bearish structure"},
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "-1", "description": "Bearish order block"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price reached OB zone"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price within OB"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

### 4.3 Fair Value Gap (FVG) Entry

An unfilled FVG acts as a magnet — price tends to return and fill the gap. Enter when price reaches the FVG.

**Buy at bullish FVG (gap up that hasn't been filled):**
```json
{
  "phase": "fvg_entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish bias"},
      {"left": "ind.m15_ob_fvg.fvg_type", "operator": "==", "right": "1", "description": "Bullish FVG present"},
      {"left": "ind.m15_ob_fvg.fvg_filled", "operator": "==", "right": "0", "description": "FVG not yet filled"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.fvg_upper", "description": "Price entering FVG"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.fvg_lower", "description": "Price within FVG bounds"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.4 OB + FVG Overlap (High Probability)

When an order block and FVG overlap, the zone has double confluence. Use `combined_partial` or `combined_all` for quick detection.

**High-probability entry — all layers align:**
```json
{
  "phase": "full_confluence_entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "ind.m15_ob_fvg.combined_all", "operator": "==", "right": "1", "description": "OB + FVG + ZigZag all align"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price in the zone"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

**Partial confluence — at least 2 of 3:**
```json
{
  "phase": "partial_confluence_entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "ind.m15_ob_fvg.combined_partial", "operator": "==", "right": "1", "description": "At least 2 layers align"},
      {"left": "_price", "operator": "<", "right": "ind.h4_smc_structure.equilibrium", "description": "In discount zone"}
    ]
  }
}
```

### 4.5 Breaker Block Entry

When a bullish OB fails (price breaks below it), the OB becomes a **breaker resistance** (`ob_type == 2`). When a bearish OB fails, it becomes a **breaker support** (`ob_type == -2`). Breakers flip polarity.

**Sell at breaker resistance (failed bullish OB):**
```json
{
  "phase": "breaker_sell",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Bearish structure"},
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "2", "description": "Breaker resistance (failed bull OB)"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price touching breaker"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price within breaker zone"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

### 4.6 Multi-Layer ZigZag Confluence

When multiple ZigZag layers agree on a swing level, that level has higher significance.

**Buy at ZigZag confluence support:**
```json
{
  "phase": "zz_confluence",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish bias"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.zz1_down", "description": "At ZZ layer 1 low"},
      {"left": "ind.m15_ob_fvg.zz1_down", "operator": "<=", "right": "ind.m15_ob_fvg.zz2_down * 1.002", "description": "ZZ1 and ZZ2 lows within 0.2% — confluence"}
    ]
  }
}
```

## 5. Combinations

| Combine With | Purpose | Role of OB_FVG |
|---|---|---|
| SMC_Structure | Complete SMC setup | Structure provides bias; OB_FVG provides entry zones |
| NW_Envelope | Mean reversion at OB | NW confirms price is at extreme; OB gives the exact level |
| RSI | Momentum at entry zone | OB defines zone; RSI confirms oversold/overbought |
| ATR | Stop loss sizing | OB defines entry; ATR ensures SL beyond OB is reasonable |
| Volume | OB validation | High volume at OB formation confirms institutional participation |

**Best combination:** SMC_Structure (H4 bias) + OB_FVG (M15 entry) + RSI (M15 momentum) — the workhorse SMC playbook.

## 6. Position Management

### Stop Loss
- **For OB entries:** SL below the OB lower boundary (for buys) or above OB upper (for sells), plus a small buffer.
- **For FVG entries:** SL below the FVG lower boundary.

```json
{
  "stop_loss": {
    "type": "indicator",
    "reference": "ind.m15_ob_fvg.ob_lower",
    "offset": "-1.0",
    "description": "SL below order block with $1 buffer"
  }
}
```

### Take Profit
- **TP1:** Opposing OB zone or FVG on higher timeframe.
- **TP2:** Next ZigZag swing level (`zz2_up` for buys).
- **TP3:** SMC_Structure swing_high (for buys) or swing_low (for sells).

### Mitigation Tracking
- Once price fills an FVG (`fvg_filled == 1`), do not re-enter at that level.
- Once an OB is mitigated (price passed through >50%), it loses power — look for the next OB.

## 7. Pitfalls

1. **Trading every OB.** Not all order blocks are equal. Prioritize OBs that formed with a strong impulse move away from the zone, and those aligned with HTF structure.
2. **Ignoring FVG fill status.** An FVG that has already been filled (`fvg_filled == 1`) is no longer a valid entry zone. Always check this field.
3. **OB in ranging market.** In a range, OBs get mitigated repeatedly. OBs work best when there is a clear trend from SMC_Structure.
4. **Too many active zones.** The indicator tracks the nearest OB/FVG. If you want multiple zones, use different timeframes (H4 OB + M15 OB) rather than trying to track 5 zones on the same timeframe.
5. **Breaker blocks in trending markets.** Breakers are reversal signals. Using them in a strong trend leads to counter-trend entries. Only use breakers when SMC_Structure confirms a CHOCH.
6. **ZigZag overfitting.** Three ZigZag layers provide confluence, but requiring all three to agree (`combined_all`) may produce very few signals. Use `combined_partial` for more trades.
7. **Entering at OB edge vs. middle.** Always wait for price to enter the zone (between `ob_lower` and `ob_upper`), not just touch the edge. Many OB touches wick through without holding.

## 8. XAUUSD-Specific Notes

- **Institutional respect:** Gold is heavily traded by central banks and institutions. Order blocks on H4 and Daily XAUUSD are among the most respected in any market. Trust H4 OBs on gold.
- **FVG fill rate:** XAUUSD fills approximately 75-85% of FVGs within 24 hours. This makes FVG entries highly reliable on M15-H1.
- **OB size:** Gold OBs tend to be $3-$15 wide on M15 and $10-$40 wide on H4. Use `ob_strength: 4` to filter weak OBs.
- **Breaker blocks:** Gold breakers are particularly powerful during London/NY session transitions. A failed Asian session OB becoming a breaker during London often produces excellent moves.
- **Session-specific OBs:** London open OBs (07:00-09:00 UTC) are the highest quality. NY open OBs (13:00-15:00 UTC) are second. Asian OBs frequently get swept.
- **FVG during news:** Major news events (NFP, FOMC) create large FVGs. These tend to fill within 1-4 hours after the event. Consider a dedicated news-FVG playbook.
- **Spread awareness:** XAUUSD spreads widen to 30-50 pips during news. Your OB entry may execute at a worse price than expected. Add spread buffer to OB boundaries during volatile sessions.
- **ZigZag on gold:** The default ZigZag depths `[5, 13, 34]` work well for M15 gold. For H4, consider `[8, 21, 55]` to capture larger institutional swings.
