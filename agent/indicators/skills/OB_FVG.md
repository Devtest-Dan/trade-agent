# OB_FVG — Order Blocks & Fair Value Gaps

## 1. Overview

The OB_FVG indicator identifies institutional order blocks (supply/demand zones where large players entered) and fair value gaps (imbalances in price delivery). It tracks order blocks through a 4-stage lifecycle: active → tested → breaker → reversed. Combined with structural bias from SMC_Structure, it provides precise entry zones.

**Indicator ID pattern:** `<timeframe>_ob_fvg` (e.g., `h4_ob_fvg`, `m15_ob_fvg`)

### Output Fields

| Field | Type | Description |
|---|---|---|
| `ob_upper` | float | Upper boundary of the nearest active order block |
| `ob_lower` | float | Lower boundary of the nearest active order block |
| `ob_type` | float | `+1` = bullish OB (demand), `-1` = bearish OB (supply), `0` = none |
| `ob_state` | float | OB lifecycle: `1` = active, `2` = tested, `3` = breaker, `4` = reversed |
| `fvg_upper` | float | Upper boundary of the nearest unfilled FVG |
| `fvg_lower` | float | Lower boundary of the nearest unfilled FVG |
| `fvg_filled` | float | `0` = gap still open, `1` = gap has been filled/mitigated |
| `bull_ob_count` | float | Total bullish OBs currently detected |
| `bear_ob_count` | float | Total bearish OBs currently detected |
| `bull_breaker_count` | float | Active bullish breaker blocks |
| `bear_breaker_count` | float | Active bearish breaker blocks |

### OB State Machine

Order blocks progress through a lifecycle:
1. **Active (1)** — freshly detected, untouched
2. **Tested (2)** — price returned and partially entered the zone (by `test_percent`)
3. **Breaker (3)** — price fully broke through the OB, flipping its polarity (failed bull OB becomes bearish resistance, vice versa)
4. **Reversed (4)** — breaker block that was itself broken through, fully invalidated

## 2. When to Use

- **Precision entries** — after SMC_Structure provides directional bias, use OB/FVG for exact entry price.
- **Supply/demand zone trading** — identify where institutional orders likely sit.
- **Gap trading** — FVGs represent inefficiency; price tends to return and fill them.
- **Breaker block reversals** — when a known OB fails (`ob_state == 3`), it flips polarity.
- **State tracking** — `ob_state` tells you whether an OB is fresh, tested, or exhausted.

## 3. Parameters Guide

| Parameter | Default | Range | Description |
|---|---|---|---|
| `test_percent` | 30.0 | 10–80 | How far price must enter the OB zone (as %) to mark it as "tested" |
| `fill_percent` | 50.0 | 20–100 | How much of an FVG must be filled (as %) before marking it as filled |
| `max_obs` | 500 | 100–2000 | Maximum order blocks to track in memory |

**Advanced (rarely changed):**

| Parameter | Default | Description |
|---|---|---|
| `bars_keep_reversed` | 50 | How many bars to keep reversed OBs before purging |

**XAUUSD recommended:** Defaults work well. Gold's large candles produce well-defined OBs.

## 4. Key Patterns & Setups

### 4.1 Bullish Order Block Entry

Price returns to a bullish OB zone after a BOS. The OB acts as demand — expect price to bounce.

**Enter long when price reaches active bullish OB:**
```json
{
  "phase": "wait_for_ob_entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure (from SMC)"},
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "1", "description": "Bullish order block detected"},
      {"left": "ind.m15_ob_fvg.ob_state", "operator": "<=", "right": "2", "description": "OB is active or tested (not breaker)"},
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
      {"left": "ind.m15_ob_fvg.ob_state", "operator": "<=", "right": "2", "description": "Active or tested"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price reached OB zone"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price within OB"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

### 4.3 Fair Value Gap (FVG) Entry

An unfilled FVG acts as a magnet — price tends to return and fill the gap. Enter when price reaches the FVG.

**Buy at unfilled bullish FVG:**
```json
{
  "phase": "fvg_entry",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish bias"},
      {"left": "ind.m15_ob_fvg.fvg_filled", "operator": "==", "right": "0", "description": "FVG not yet filled"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.fvg_upper", "description": "Price entering FVG"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.fvg_lower", "description": "Price within FVG bounds"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.4 Breaker Block Entry

When an OB fails (price breaks through it), the OB becomes a **breaker block** (`ob_state == 3`). Breakers flip polarity — a failed bullish OB becomes resistance, a failed bearish OB becomes support.

**Sell at breaker block (failed bullish OB now acting as resistance):**
```json
{
  "phase": "breaker_sell",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Bearish structure"},
      {"left": "ind.m15_ob_fvg.ob_state", "operator": "==", "right": "3", "description": "Breaker block (failed OB)"},
      {"left": "_price", "operator": ">=", "right": "ind.m15_ob_fvg.ob_lower", "description": "Price touching breaker"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price within breaker zone"}
    ]
  },
  "transitions": [{"target": "execute_sell"}]
}
```

### 4.5 OB + FVG Overlap (High Probability)

When an order block and FVG overlap, the zone has double confluence.

**OB and FVG overlap detection:**
```json
{
  "phase": "ob_fvg_confluence",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
      {"left": "ind.m15_ob_fvg.ob_type", "operator": "==", "right": "1", "description": "Bullish OB present"},
      {"left": "ind.m15_ob_fvg.fvg_filled", "operator": "==", "right": "0", "description": "Unfilled FVG also present"},
      {"left": "_price", "operator": "<=", "right": "ind.m15_ob_fvg.ob_upper", "description": "Price in the OB zone"}
    ]
  },
  "transitions": [{"target": "execute_buy"}]
}
```

### 4.6 OB Count as Market Pressure Gauge

High bull_ob_count vs bear_ob_count reveals underlying pressure.

**Bullish pressure dominance:**
```json
{
  "phase": "pressure_filter",
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_ob_fvg.bull_ob_count", "operator": ">", "right": "ind.h4_ob_fvg.bear_ob_count", "description": "More bullish OBs than bearish — bullish pressure"}
    ]
  }
}
```

## 5. Combinations

| Combine With | Purpose | Role of OB_FVG |
|---|---|---|
| SMC_Structure | Complete SMC setup | Structure provides bias; OB_FVG provides entry zones |
| TPO | Level confluence | OB at POC = very high probability zone |
| NW_Envelope | Mean reversion at OB | NW confirms price is at extreme; OB gives the exact level |
| RSI | Momentum at entry zone | OB defines zone; RSI confirms oversold/overbought |
| ATR | Stop loss sizing | OB defines entry; ATR ensures SL beyond OB is reasonable |

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
- **TP1:** Opposing OB zone or FVG boundary.
- **TP2:** SMC_Structure ref_high (for buys) or ref_low (for sells).
- **TP3:** TPO POC or VAH/VAL levels.

### Mitigation Tracking
- Once price fills an FVG (`fvg_filled == 1`), do not re-enter at that level.
- Once an OB reaches state 3 (breaker) or 4 (reversed), its original role is gone — only use breakers for reverse entries.

## 7. Pitfalls

1. **Trading every OB.** Not all order blocks are equal. Prioritize OBs that are active (`ob_state == 1`) or freshly tested (`ob_state == 2`), and those aligned with HTF structure.
2. **Ignoring FVG fill status.** An FVG that has been filled (`fvg_filled == 1`) is no longer a valid entry zone. Always check this field.
3. **OB in ranging market.** In a range, OBs get mitigated repeatedly. OBs work best when there is a clear trend from SMC_Structure.
4. **Confusing OB state with type.** `ob_type` tells you direction (+1/-1). `ob_state` tells you lifecycle stage (1-4). Both matter for entry decisions.
5. **Breaker blocks in trending markets.** Breakers are reversal signals. Using them in a strong trend leads to counter-trend entries. Only use breakers when SMC_Structure confirms a CHoCH.
6. **Entering at OB edge vs. middle.** Always wait for price to enter the zone (between `ob_lower` and `ob_upper`), not just touch the edge. Many OB touches wick through without holding.

## 8. XAUUSD-Specific Notes

- **Institutional respect:** Gold is heavily traded by central banks and institutions. Order blocks on H4 and Daily XAUUSD are among the most respected in any market.
- **FVG fill rate:** XAUUSD fills approximately 75–85% of FVGs within 24 hours. This makes FVG entries highly reliable on M15-H1.
- **OB size:** Gold OBs tend to be $3–$15 wide on M15 and $10–$40 wide on H4.
- **Breaker blocks:** Gold breakers are particularly powerful during London/NY session transitions. A failed Asian session OB becoming a breaker during London often produces excellent moves.
- **Session-specific OBs:** London open OBs (07:00–09:00 UTC) are the highest quality. NY open OBs (13:00–15:00 UTC) are second. Asian OBs frequently get swept.
- **FVG during news:** Major news events (NFP, FOMC) create large FVGs. These tend to fill within 1–4 hours after the event.
- **Spread awareness:** XAUUSD spreads widen to 30–50 pips during news. Add spread buffer to OB boundaries during volatile sessions.
