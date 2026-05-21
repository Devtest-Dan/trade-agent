# SMC KAO Resumption Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Pine v6 TradingView strategy that combines a full port of `SMC Structure (KAO) — KAO_v1.7` + `Kernel Bollinger Band` into one file, then layers state-machine, entry-trigger, exit, sizing, alerts and visuals per spec `2026-05-21-smc-kao-resumption-design.md`.

**Architecture:** Single Pine v6 `strategy()` script. KAO_v1.7 structure code (CHoCH/BOS/HH/HL/LL/LH/OB/FVG) is ported verbatim from `SMC_Structure_OBFVG_KAO` (script ID `USER;043650bf417f4f7891aa5d78350ff769`); KBB calculation is ported from `Kernel Bollinger Band` (script ID `USER;002961e1925a46fead23d63d3782b84d`). Strategy state tracks trend direction since last opposite CHoCH plus rolling impulse extremes; entries trigger on Kernel BB wick rejection while in discount/premium zone; exits use frozen-SL + structural trail + opposite-CHoCH force-close.

**Tech Stack:** Pine Script v6 (TradingView native), TradingView MCP server (CDP-controlled desktop client) for compile / verify / data-extraction. Local source backup committed to `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine` in the `trade-agent` git repo.

**Spec:** `D:\trade-agent\docs\superpowers\specs\2026-05-21-smc-kao-resumption-design.md`

**Free-plan constraint:** TradingView max 2 indicators/chart. The new strategy = 1 slot. Verification overlays must swap indicators in/out sequentially — never overlay all three simultaneously.

---

## File Structure

| File | Responsibility | Owner |
|---|---|---|
| `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine` | Local source backup of the strategy. Single file; committed to git. | New (created Task 3) |
| TradingView script `SMC_KAO_Resumption_Strategy` | Live editable copy on TradingView. Same content as local file. Created via `pine_new` + `pine_set_source`. | New (created Task 3) |
| `D:\trade-agent\pinescript\kao_v17_reference.pine` | Read-only snapshot of `SMC_Structure_OBFVG_KAO` source for porting reference. NOT for editing. | New (created Task 1) |
| `D:\trade-agent\pinescript\kbb_reference.pine` | Read-only snapshot of `Kernel Bollinger Band` source for porting reference. | New (created Task 2) |
| `D:\trade-agent\docs\superpowers\specs\2026-05-21-smc-kao-resumption-design.md` | Design spec (existing). | Reference only. |

---

## Conventions for every task

- **"Compile"** = call `pine_smart_compile` (the MCP tool). Expected output: `success: true`, `errors: []`. If errors → fix before next step.
- **"Save"** = call `pine_save`. Persists the current editor source as the script on TradingView's servers.
- **"Local backup"** = after `pine_save` succeeds, write the same source to the local `.pine` file path; `git add` and `git commit` scoped only to that file (per Daniel's git scoping rule from memory).
- **"Indicator overlay swap"** = use `chart_manage_indicator` to remove one indicator and add another, respecting the 2-slot free-plan limit.
- **Pine TDD substitute:** Pine has no unit test framework. "Tests" in this plan are empirical:
  1. `pine_smart_compile` succeeds, zero errors.
  2. After load on chart, `data_get_pine_labels` / `data_get_pine_lines` / `data_get_pine_boxes` / `data_get_study_values` returns the expected reference output.
- **Commit message style** (match repo): `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...` — see `git log --oneline -10`.
- **Working directory:** Commands assume cwd = `D:\trade-agent`. Bash tool resets cwd between calls — prepend `cd D:/trade-agent &&` to every git command.

---

## Task 1: Snapshot KAO_v1.7 source for porting reference

**Files:**
- Create: `D:\trade-agent\pinescript\kao_v17_reference.pine`

- [ ] **Step 1: Open KAO_v1.7 in the Pine Editor**

Call MCP tool: `mcp__tradingview__pine_open` with `name = "SMC Structure (KAO) — KAO_v1.7"`.

Expected: `success: true`, `script_id: "USER;043650bf417f4f7891aa5d78350ff769"`, `lines: ~2966`, `opened: true`.

- [ ] **Step 2: Retrieve full source**

Call MCP tool: `mcp__tradingview__pine_get_source` (no args — gets current editor content).

Expected: `success: true`, `line_count: ~2966`. **Warning: ~200KB return — large context burn. Acceptable here because we save it to disk and reference offline thereafter.**

- [ ] **Step 3: Write full source to local reference file**

Use Write tool with the `source` string returned by Step 2.

Path: `D:\trade-agent\pinescript\kao_v17_reference.pine`

- [ ] **Step 4: Inventory the structural-detection sections**

Use Grep on the saved file to locate the porting targets:

```
Grep pattern: "indicator\\(" → find indicator() declaration line
Grep pattern: "input\\." → find all input declarations
Grep pattern: "ta.pivothigh|ta.pivotlow" → find pivot logic
Grep pattern: "CHoCH|CHOCH|ChoCh" → find CHoCH detection / labeling
Grep pattern: "BOS|BoS" → find BOS detection / labeling
Grep pattern: "OB \\(|orderBlock|orderblock" → find OB drawing
Grep pattern: "FVG|fairValueGap" → find FVG drawing
Grep pattern: "label.new|box.new|line.new" → find all visual drawings
```

Record the line ranges of each section in a comment block at the top of `kao_v17_reference.pine`:

```
// ===== PORTING INDEX =====
// Inputs: lines A..B
// Pivot logic: lines C..D
// Major structure (HH/HL/LL/LH): lines E..F
// CHoCH detection: lines G..H
// BOS detection: lines I..J
// OB drawing: lines K..L
// FVG drawing: lines M..N
// Plot statements: lines O..P
// =========================
```

- [ ] **Step 5: Commit reference snapshot**

```bash
cd D:/trade-agent && git add pinescript/kao_v17_reference.pine && git commit -m "chore: snapshot SMC KAO v1.7 source for porting reference"
```

---

## Task 2: Snapshot Kernel Bollinger Band source for porting reference

**Files:**
- Create: `D:\trade-agent\pinescript\kbb_reference.pine`

- [ ] **Step 1: Open Kernel Bollinger Band script**

Call MCP tool: `mcp__tradingview__pine_open` with `name = "Kernel Bollinger Band"`.

Expected: `success: true`, `script_id: "USER;002961e1925a46fead23d63d3782b84d"`.

- [ ] **Step 2: Retrieve source**

Call `mcp__tradingview__pine_get_source`. Expected: `success: true`, line_count likely 30–150.

- [ ] **Step 3: Write to local reference**

Path: `D:\trade-agent\pinescript\kbb_reference.pine`

- [ ] **Step 4: Identify KBB inputs and outputs**

Use Read tool on the file. Note the kernel function (likely Nadaraya-Watson, Rational Quadratic, or Gaussian), the bandwidth/length input names, the std-dev multiplier input, and the three `plot()` statements (Basis / Upper / Lower).

- [ ] **Step 5: Commit reference snapshot**

```bash
cd D:/trade-agent && git add pinescript/kbb_reference.pine && git commit -m "chore: snapshot Kernel Bollinger Band source for porting reference"
```

---

## Task 3: Create strategy skeleton — port KAO_v1.7 structure code verbatim

**Files:**
- Create: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`
- Create: TradingView script `SMC_KAO_Resumption_Strategy`

- [ ] **Step 1: Build the skeleton header**

Open a new editor in TradingView via `mcp__tradingview__pine_new` (no args). Expected: `success: true`, opens with default `My script` template.

Replace the editor content via `pine_set_source` with this skeleton (insert KAO_v1.7's full original body verbatim from `kao_v17_reference.pine` between the marked sections — DO NOT paraphrase, copy character-by-character):

```pine
// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © danielshobhan

//@version=6
strategy("SMC KAO Resumption Strategy v1.0",
     overlay              = true,
     pyramiding           = 1,
     default_qty_type     = strategy.percent_of_equity,
     default_qty_value    = 100,
     initial_capital      = 10000,
     calc_on_every_tick   = false,
     process_orders_on_close = true,
     commission_type      = strategy.commission.percent,
     commission_value     = 0.0)

// =========================================================
// PORTED SECTION 1: SMC KAO v1.7 — Inputs
// (verbatim from SMC_Structure_OBFVG_KAO)
// =========================================================
// <<< INSERT all input.* declarations from kao_v17_reference.pine here >>>

// =========================================================
// PORTED SECTION 2: SMC KAO v1.7 — Pivot + Structure detection
// (verbatim from SMC_Structure_OBFVG_KAO)
// =========================================================
// <<< INSERT pivot detection, swing labeling (HH/HL/LL/LH), CHoCH, BOS,
//     OB, FVG, EQH/EQL detection code from kao_v17_reference.pine here >>>

// =========================================================
// PORTED SECTION 3: SMC KAO v1.7 — Visual drawings
// (verbatim from SMC_Structure_OBFVG_KAO)
// =========================================================
// <<< INSERT all label.new / box.new / line.new from kao_v17_reference.pine here >>>

// =========================================================
// PLACEHOLDERS (built up by later tasks)
// =========================================================
// Kernel BB calc — Task 5
// State machine — Task 7
// Entry logic — Task 9
// Exit logic — Task 11
// Position sizing — Task 12
// Alerts — Task 14
// Visual layer — Task 15
```

**Important:** The KAO_v1.7 script declares itself as `indicator(...)`. The ported version uses `strategy(...)` instead. Replace ONLY the `indicator(...)` line; do not modify the rest. All KAO inputs, calcs, and drawings stay byte-identical.

- [ ] **Step 2: Compile**

Call `mcp__tradingview__pine_smart_compile`. Expected: `success: true`, `errors: []`.

If errors:
- Most likely cause: Pine doesn't allow some functions (e.g., `request.security` with certain args) inside a `strategy()` that they allow in an `indicator()` — check error messages.
- Second likely cause: `max_lines_count`, `max_boxes_count`, `max_labels_count` declared via the `indicator()` call need to be specified on the `strategy()` call instead. Re-add them to the `strategy(...)` declaration.

Fix until clean. **Do not proceed to Step 3 until compile is clean.**

- [ ] **Step 3: Save to TradingView**

Call `mcp__tradingview__pine_save` with `name = "SMC_KAO_Resumption_Strategy"` (verify the parameter name via `ToolSearch` first if pine_save isn't loaded).

Expected: `success: true`, a new script ID returned. Record this ID.

- [ ] **Step 4: Write local backup**

Use Write tool to save the exact same source to `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`.

- [ ] **Step 5: Commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: scaffold SMC KAO Resumption Strategy with KAO v1.7 structure port"
```

---

## Task 4: Verify KAO structure parity (sequential indicator swap)

**Files:**
- Modify (potentially): `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine` only if parity fails

**Setup:** Chart at `TICKMILL:EURUSD` H1 (current state). Both indicators currently loaded: KAO_v1.7 + Kernel BB. The new strategy is saved but not yet on chart.

- [ ] **Step 1: Capture KAO_v1.7 baseline data**

With KAO_v1.7 on chart:

```
mcp__tradingview__data_get_pine_labels(study_filter="SMC", max_labels=200)
mcp__tradingview__data_get_pine_boxes(study_filter="SMC")
mcp__tradingview__data_get_pine_lines(study_filter="SMC")
```

Write the returned JSON to a temp file: `D:\trade-agent\pinescript\_kao_baseline.json` (so we don't have to re-capture if subsequent steps go wrong).

- [ ] **Step 2: Swap indicators — remove KAO_v1.7, remove Kernel BB, add new strategy**

```
mcp__tradingview__chart_manage_indicator(action="remove", entity_id="ZRP0ST")   # KAO_v1.7
mcp__tradingview__chart_manage_indicator(action="remove", entity_id="tUueYn")   # Kernel BB
mcp__tradingview__chart_manage_indicator(action="add", name="SMC KAO Resumption Strategy v1.0")
```

Verify via `chart_get_state` that the new strategy is the only loaded indicator/study.

- [ ] **Step 3: Capture new-strategy structure data**

```
mcp__tradingview__data_get_pine_labels(study_filter="Resumption", max_labels=200)
mcp__tradingview__data_get_pine_boxes(study_filter="Resumption")
mcp__tradingview__data_get_pine_lines(study_filter="Resumption")
```

Write to: `D:\trade-agent\pinescript\_strategy_kao_port.json`.

- [ ] **Step 4: Diff and verify**

Compare:
- Label texts + prices: every label in `_kao_baseline.json` must have a matching entry in `_strategy_kao_port.json` with identical `text` and `price` (within 5 decimal places).
- Box zones: every `{high, low}` in baseline must match in port.
- Horizontal line levels: every price in baseline must match in port.

If mismatch:
- Likely cause: missed a copy block, or KAO uses `varip` / `var` initializations that need reordering when wrapped in a strategy.
- Fix by re-comparing the inserted blocks in `smc-kao-resumption-strategy.pine` against `kao_v17_reference.pine`. Re-port the divergent section.
- Re-compile, re-save, re-capture. Loop until diff is empty.

- [ ] **Step 5: Restore the original chart state**

```
mcp__tradingview__chart_manage_indicator(action="add", name="SMC Structure (KAO) — KAO_v1.7")
# Strategy still loaded — now 2 indicators, at free-plan limit
```

(Kernel BB stays off until Task 6.)

- [ ] **Step 6: Commit verification artifacts**

```bash
cd D:/trade-agent && git add pinescript/_kao_baseline.json pinescript/_strategy_kao_port.json && git commit -m "chore: KAO structure parity verification artifacts for resumption strategy"
```

---

## Task 5: Port Kernel Bollinger Band calculation into the strategy

**Files:**
- Modify: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`

- [ ] **Step 1: Locate the KBB placeholder in the strategy source**

Open the strategy script in the editor:

```
mcp__tradingview__pine_open(name="SMC_KAO_Resumption_Strategy")
mcp__tradingview__pine_get_source
```

Find the line `// Kernel BB calc — Task 5`.

- [ ] **Step 2: Insert the KBB code block**

Replace the placeholder line with the KBB code, verbatim from `kbb_reference.pine`, wrapped in a section marker:

```pine
// =========================================================
// PORTED SECTION 4: Kernel Bollinger Band
// (verbatim from `Kernel Bollinger Band` script)
// =========================================================
// <<< INSERT kbb_reference.pine inputs (group inputs under "Kernel Bollinger Band") >>>
// <<< INSERT kbb_reference.pine kernel basis calculation >>>
// <<< INSERT kbb_reference.pine stddev + upper/lower band calculation >>>
kbb_basis = <variable name from kbb_reference.pine>
kbb_upper = <variable name from kbb_reference.pine>
kbb_lower = <variable name from kbb_reference.pine>

plot(kbb_basis, "kbb_basis", color = color.new(color.orange, 0))
plot(kbb_upper, "kbb_upper", color = color.new(color.aqua, 0))
plot(kbb_lower, "kbb_lower", color = color.new(color.aqua, 0))
```

Use `mcp__tradingview__pine_set_source` to write the modified full source back.

- [ ] **Step 3: Compile**

`mcp__tradingview__pine_smart_compile`. Expected: clean.

If duplicate input title errors (KAO + KBB both use generic names like `"Length"`): prefix KBB inputs with `"KBB "` (e.g., `"KBB Length"`, `"KBB Bandwidth"`).

- [ ] **Step 4: Save**

`mcp__tradingview__pine_save`.

- [ ] **Step 5: Update local backup**

Write the updated source to `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`.

- [ ] **Step 6: Commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: port Kernel Bollinger Band calc into resumption strategy"
```

---

## Task 6: Verify KBB parity

**Setup:** Chart has KAO_v1.7 + new strategy loaded (per Task 4 Step 5).

- [ ] **Step 1: Swap — remove KAO_v1.7, add Kernel BB indicator**

```
mcp__tradingview__chart_manage_indicator(action="remove", name="SMC Structure (KAO) — KAO_v1.7")
mcp__tradingview__chart_manage_indicator(action="add", name="Kernel Bollinger Band")
```

Now loaded: Kernel BB indicator + new strategy (which also computes KBB internally).

- [ ] **Step 2: Capture both KBB outputs**

```
mcp__tradingview__data_get_study_values
```

Expected studies returned:
- `Kernel Bollinger Band` with keys `Basis`, `Upper`, `Lower`
- `SMC KAO Resumption Strategy v1.0` with keys including `kbb_basis`, `kbb_upper`, `kbb_lower`

- [ ] **Step 3: Verify values match**

Compare:
- `Kernel Bollinger Band.Basis` ≈ `Strategy.kbb_basis` (within 0.5 × mintick)
- Same for Upper / Lower

If mismatch:
- Most likely cause: input default values differ. Check the strategy's KBB input defaults vs. what the standalone Kernel BB indicator has saved as its current settings (use `mcp__tradingview__chart_get_state` + check the indicator settings via `pine_get_source` of `kbb_reference.pine`).
- Set the strategy's KBB inputs to exactly match the user's current Kernel BB indicator settings (length, multiplier, bandwidth, source).

- [ ] **Step 4: Remove the standalone Kernel BB indicator**

```
mcp__tradingview__chart_manage_indicator(action="remove", name="Kernel Bollinger Band")
mcp__tradingview__chart_manage_indicator(action="add", name="SMC Structure (KAO) — KAO_v1.7")
```

Final state: KAO_v1.7 + strategy on chart. The strategy now visually carries both KAO + KBB; KAO_v1.7 stays for ongoing cross-check.

- [ ] **Step 5: Commit (no code change — verification only)**

Skip commit. No file changed.

---

## Task 7: Add state machine (trendDir, legHigh, legLow, legMid, armed, barsInTrend)

**Files:**
- Modify: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`

This task references KAO_v1.7's CHoCH and major-pivot variables. The executing agent must **inspect `kao_v17_reference.pine`** to find the actual variable names KAO uses (e.g., `isBullCHoCH`, `lastBullCHoCH`, `chochUp`, `swingHigh`, `swingLow`, etc.) — names vary by author. Substitute the correct names below where `<KAO_*>` placeholders appear.

- [ ] **Step 1: Identify KAO's CHoCH and swing variables**

Use Grep on `kao_v17_reference.pine`:

```
Grep "CHoCH" → find the boolean flag(s) that fire when a CHoCH is detected
Grep "BOS" → same for BOS
Grep "swing.*[Hh]igh|pivot.*[Hh]igh" → find the major swing-high variable
Grep "swing.*[Ll]ow|pivot.*[Ll]ow" → find the major swing-low variable
```

Record findings in a code comment:

```pine
// KAO variables used:
//   <KAO_chochUp>    = bullish CHoCH event (bool, true on the bar it fires)
//   <KAO_chochDown>  = bearish CHoCH event
//   <KAO_chochPrice> = price at which the CHoCH was confirmed
```

- [ ] **Step 2: Insert state machine code**

Replace the `// State machine — Task 7` placeholder with:

```pine
// =========================================================
// STATE MACHINE
// =========================================================
var int   trendDir    = 0           // +1 bull, -1 bear, 0 none
var float legHigh     = na
var float legLow      = na
var int   barsInTrend = 0
var bool  armed       = false       // re-entry gate

// Detect major CHoCH events from KAO ported code
bool chochUp   = <KAO_chochUp>     // <<< substitute with actual KAO var
bool chochDown = <KAO_chochDown>   // <<< substitute with actual KAO var

// Trend flip: opposite-direction major CHoCH resets the leg
if chochUp and trendDir != 1
    trendDir    := 1
    legHigh     := high
    legLow      := low
    barsInTrend := 0
    armed       := true
else if chochDown and trendDir != -1
    trendDir    := -1
    legHigh     := high
    legLow      := low
    barsInTrend := 0
    armed       := true
else if trendDir != 0
    legHigh     := math.max(nz(legHigh, high), high)
    legLow      := math.min(nz(legLow, low), low)
    barsInTrend := barsInTrend + 1

legMid = (legHigh + legLow) / 2.0

// Re-arm logic re-runs every bar (re-arming requires no open position)
inputReArmExtreme = input.bool(true,  "Re-arm on new HH/LL extreme", group = "Strategy")
inputReArmBasis   = input.bool(true,  "Re-arm on basis touch",      group = "Strategy")

var float lastLegHigh = na
var float lastLegLow  = na
bool newExtreme       = false
if trendDir == 1 and not na(legHigh) and (na(lastLegHigh) or legHigh > lastLegHigh)
    newExtreme   := true
    lastLegHigh  := legHigh
if trendDir == -1 and not na(legLow) and (na(lastLegLow) or legLow < lastLegLow)
    newExtreme   := true
    lastLegLow   := legLow

bool basisTouch =
     (trendDir == 1  and low  <= kbb_basis) or
     (trendDir == -1 and high >= kbb_basis)

if strategy.position_size == 0 and not armed
    if (inputReArmExtreme and newExtreme) or (inputReArmBasis and basisTouch)
        armed := true

// Diagnostic plots (data window only)
plot(trendDir,    "trendDir",    color = na, display = display.data_window)
plot(legHigh,     "legHigh",     color = na, display = display.data_window)
plot(legLow,      "legLow",      color = na, display = display.data_window)
plot(legMid,      "legMid",      color = na, display = display.data_window)
plot(armed ? 1 : 0, "armed",     color = na, display = display.data_window)
plot(barsInTrend, "barsInTrend", color = na, display = display.data_window)
```

**Critical:** when substituting `<KAO_chochUp>` / `<KAO_chochDown>`, use the variable names from the KAO code AS IT EXISTS IN THE STRATEGY FILE (the ported version). If KAO has them named `bull_choch_event` and `bear_choch_event`, use those.

- [ ] **Step 3: Compile**

Expected: clean.

If errors:
- `Undeclared identifier 'kbb_basis'` → KBB code (Task 5) is below the state machine; move state machine below KBB or hoist KBB to be earlier in the file.
- `Cannot modify a 'var' variable from inside an if block without ':='` → use `:=`, not `=`.

- [ ] **Step 4: Save + local backup + commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: state machine for SMC KAO resumption strategy"
```

---

## Task 8: Verify state machine via data window

**Files:** verification only.

- [ ] **Step 1: Inspect current bar values**

```
mcp__tradingview__data_get_study_values
```

Expected for `SMC KAO Resumption Strategy v1.0`:
- `trendDir` ∈ {+1, -1, 0}
- `legHigh` > `legLow`
- `legMid` ≈ midpoint of legHigh and legLow
- `barsInTrend` > 0 if trendDir is set
- `armed` ∈ {0, 1}

- [ ] **Step 2: Scrub history — verify resets at each major CHoCH**

Use `mcp__tradingview__chart_scroll_to_date` to jump to a few historical bars BEFORE and AFTER each CHoCH in the labels captured at the start of this conversation:

- Bullish CHoCH at price 1.14689 — scroll to that bar
- Bearish CHoCH at price 1.18298 — scroll to that bar

Expected behavior: at the bar where each CHoCH fires, `trendDir` flips, `legHigh` resets to that bar's `high`, `legLow` to that bar's `low`, `barsInTrend` resets to 0.

If wrong: re-check the `<KAO_chochUp>`/`<KAO_chochDown>` substitution. Some KAO scripts fire the CHoCH boolean N bars AFTER the bar where the CHoCH actually happened (because of pivot confirmation lag). If that's the case, document it; the legHigh/legLow reset bar will be the "confirmation" bar, not the actual swing bar. This is acceptable as long as it's consistent.

- [ ] **Step 3: Scroll back to current bar**

```
mcp__tradingview__chart_scroll_to_date(date="<today>")
```

(Or omit and let chart auto-position to latest.)

- [ ] **Step 4: No commit (verification only)**

---

## Task 9: Add entry logic (long + short)

**Files:**
- Modify: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`

- [ ] **Step 1: Add direction input**

Above the `// Entry logic — Task 9` placeholder, in the inputs block:

```pine
inputDirection    = input.string("Both",  "Direction",                 options = ["Both", "Long only", "Short only"], group = "Strategy")
inputMinBarsTrend = input.int(5,          "Min bars in new trend before entry", minval = 1, maxval = 100, group = "Strategy")
```

- [ ] **Step 2: Replace the `// Entry logic — Task 9` placeholder**

```pine
// =========================================================
// ENTRY TRIGGERS
// =========================================================
bool allowLong  = inputDirection != "Short only"
bool allowShort = inputDirection != "Long only"

bool longCond =
     allowLong
     and trendDir == 1
     and armed
     and barsInTrend >= inputMinBarsTrend
     and low      < legMid
     and low      < kbb_lower
     and close    > kbb_lower
     and close    > open
     and not na(kbb_lower)

bool shortCond =
     allowShort
     and trendDir == -1
     and armed
     and barsInTrend >= inputMinBarsTrend
     and high     > legMid
     and high     > kbb_upper
     and close    < kbb_upper
     and close    < open
     and not na(kbb_upper)

// (strategy.entry calls come in Task 12 — for now just mark visually)
plotshape(longCond,  title="Long Signal",  location=location.belowbar, style=shape.triangleup,   color=color.new(color.lime, 0), size=size.tiny)
plotshape(shortCond, title="Short Signal", location=location.abovebar, style=shape.triangledown, color=color.new(color.red,  0), size=size.tiny)
```

- [ ] **Step 3: Compile, save, local backup, commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: entry trigger conditions + signal shapes"
```

---

## Task 10: Verify entry markers visually

**Files:** verification only.

- [ ] **Step 1: Capture entry signals from chart**

```
mcp__tradingview__data_get_pine_labels(study_filter="Resumption", max_labels=200)
```

(`plotshape` outputs aren't labels — they're shapes. Use a screenshot instead.)

- [ ] **Step 2: Screenshot the chart**

```
mcp__tradingview__capture_screenshot(region="chart")
```

Visually verify:
- Lime ▲ triangles BELOW bars only in bullish trend AND in discount zone AND on bars that wicked below KBB lower band but closed above it.
- Red ▼ triangles ABOVE bars only in bearish trend AND in premium zone AND on bars that wicked above KBB upper band but closed below it.

- [ ] **Step 3: Sanity check at least 3 markers by hand**

Scroll to 3 different markers via `chart_scroll_to_date`. For each, verify the conditions held on that bar:
- `data_get_study_values` shows trendDir matches the signal side, armed=1, low/high vs legMid as expected.

If a marker fires where it shouldn't (false positive): identify which condition didn't apply. Most common cause: `kbb_lower` warmup NaN handling. Check the `not na()` guards.

- [ ] **Step 4: No commit (verification only)**

---

## Task 11: Add exit logic (frozen SL + structural trail + opposite-CHoCH force-close)

**Files:**
- Modify: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`

- [ ] **Step 1: Add SL buffer input**

```pine
inputSLBuffer = input.float(0.0, "SL buffer (price units)", minval = 0.0, group = "Strategy")
```

- [ ] **Step 2: Replace `// Exit logic — Task 11` placeholder**

```pine
// =========================================================
// EXIT LOGIC
// =========================================================
// Frozen references — captured at entry
var float entryPrice    = na
var float frozenSL      = na
var float trailSL       = na   // ratchets in profit direction; never loosens
var int   entryDir      = 0    // +1 long / -1 short

// Capture pivots from KAO ported code — substitute actual KAO pivot var names
// after grepping kao_v17_reference.pine.
bool isConfirmedPivotLow  = <KAO_isPivotLowConfirmed>
bool isConfirmedPivotHigh = <KAO_isPivotHighConfirmed>
float confirmedPivotLow   = <KAO_pivotLowPrice>
float confirmedPivotHigh  = <KAO_pivotHighPrice>

// On confirmed pivot, ratchet the trail
if strategy.position_size > 0 and isConfirmedPivotLow and confirmedPivotLow > entryPrice
    trailSL := math.max(nz(trailSL, frozenSL), confirmedPivotLow)
if strategy.position_size < 0 and isConfirmedPivotHigh and confirmedPivotHigh < entryPrice
    trailSL := math.min(nz(trailSL, frozenSL), confirmedPivotHigh)

// Exit reasons (priority: SL > trail > CHoCH)
bool exitByStop_long  = strategy.position_size > 0 and low  <= nz(trailSL, frozenSL)
bool exitByStop_short = strategy.position_size < 0 and high >= nz(trailSL, frozenSL)
bool exitByCHoCH      =
     (strategy.position_size > 0 and chochDown) or
     (strategy.position_size < 0 and chochUp)

// Wire exits — actual strategy.exit / strategy.close calls
if exitByStop_long
    strategy.exit(id = "Long SL", from_entry = "Long", stop = nz(trailSL, frozenSL), comment = trailSL != frozenSL ? "TRAIL" : "SL")
if exitByStop_short
    strategy.exit(id = "Short SL", from_entry = "Short", stop = nz(trailSL, frozenSL), comment = trailSL != frozenSL ? "TRAIL" : "SL")
if exitByCHoCH
    strategy.close_all(comment = "CHOCH")

// Reset on flat
if strategy.position_size == 0
    entryPrice := na
    frozenSL   := na
    trailSL    := na
    entryDir   := 0
```

**Important on Pine `strategy.exit`:** The `stop` argument must be a *price level*, and the order is registered with the broker as a stop order. Pine's strategy engine handles the trigger natively — you do NOT need the manual `low <= trailSL` check. Simplify by submitting the stop order once and letting it adjust:

Cleaner pattern (use this instead of the above hand-rolled trigger):

```pine
if strategy.position_size > 0
    strategy.exit(id = "Long SL/Trail", from_entry = "Long", stop = nz(trailSL, frozenSL), comment = "STOP")
if strategy.position_size < 0
    strategy.exit(id = "Short SL/Trail", from_entry = "Short", stop = nz(trailSL, frozenSL), comment = "STOP")
if exitByCHoCH
    strategy.close_all(comment = "CHOCH")
```

Re-register the stop on every bar with the latest `trailSL` — Pine cancels and re-issues. CHoCH force-close uses `strategy.close_all`.

- [ ] **Step 3: Compile**

If errors: usually `strategy.exit` requires the entry order to exist first — Task 12 adds the entries. For Task 11, the exit code is dormant until Task 12 wires entries; this is OK.

- [ ] **Step 4: Save, backup, commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: exit logic — frozen SL, structural trail, opposite-CHoCH force-close"
```

---

## Task 12: Position sizing + wire strategy.entry

**Files:**
- Modify: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`

- [ ] **Step 1: Add risk % input**

```pine
inputRiskPct = input.float(1.0, "Risk % per trade", minval = 0.1, maxval = 5.0, step = 0.1, group = "Strategy")
```

- [ ] **Step 2: Replace `// Position sizing — Task 12` placeholder**

```pine
// =========================================================
// ENTRY EXECUTION (position sizing + strategy.entry)
// =========================================================
if longCond
    initialSL := legLow - inputSLBuffer
    riskDist  := math.abs(close - initialSL)
    qty       := riskDist > 0 ? (strategy.equity * inputRiskPct / 100.0) / riskDist : 0.0
    if qty > 0
        strategy.entry(id = "Long", direction = strategy.long, qty = qty, comment = "L_DISC_KBB")
        entryPrice := close
        frozenSL   := initialSL
        trailSL    := initialSL
        entryDir   := 1
        armed      := false

if shortCond
    initialSL := legHigh + inputSLBuffer
    riskDist  := math.abs(initialSL - close)
    qty       := riskDist > 0 ? (strategy.equity * inputRiskPct / 100.0) / riskDist : 0.0
    if qty > 0
        strategy.entry(id = "Short", direction = strategy.short, qty = qty, comment = "S_PREM_KBB")
        entryPrice := close
        frozenSL   := initialSL
        trailSL    := initialSL
        entryDir   := -1
        armed      := false
```

**Add helper var declarations** at the top of the strategy section (before any usage):

```pine
var float initialSL = na
var float riskDist  = na
var float qty       = na
```

- [ ] **Step 3: Compile, save, local backup, commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: position sizing (risk %) and strategy.entry wiring"
```

---

## Task 13: Manual review of first 5 backtested trades

**Files:** verification only.

- [ ] **Step 1: Open Strategy Tester**

```
mcp__tradingview__ui_open_panel(panel="strategy_tester")   # if separate tool — else this auto-opens with strategy on chart
```

- [ ] **Step 2: Capture strategy results**

```
mcp__tradingview__data_get_strategy_results
mcp__tradingview__data_get_trades
```

Expected: a list of trades with entry time / price / size / exit time / price / PnL.

- [ ] **Step 3: For each of the first 5 trades, verify by hand**

For trade #1:
- Scroll to entry bar (`chart_scroll_to_date` with the entry time).
- Capture `data_get_study_values` at that bar: confirm `trendDir`, `armed`, `legMid`, `kbb_upper`/`lower` at expected positions.
- Confirm entry side matches `trendDir`.
- Scroll to exit bar; verify exit reason via `data_get_trades` `exit_comment` field (`STOP` / `CHOCH`).

If a trade looks wrong (e.g., entry in premium zone with `trendDir == 1`): root-cause and fix. Likely culprit: the re-arm logic — if `armed` stays true when it shouldn't, multiple entries can fire in the same correction.

- [ ] **Step 4: Capture screenshot for record**

```
mcp__tradingview__capture_screenshot(region="strategy_tester")
```

Save to: `D:\trade-agent\docs\superpowers\plans\artifacts\2026-05-21-first-5-trades.png` (create the `artifacts/` dir if missing).

- [ ] **Step 5: Commit screenshot only**

```bash
cd D:/trade-agent && git add docs/superpowers/plans/artifacts/2026-05-21-first-5-trades.png && git commit -m "chore: backtest first-5-trades sanity screenshot"
```

---

## Task 14: Add alerts (5 conditions)

**Files:**
- Modify: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`

- [ ] **Step 1: Replace `// Alerts — Task 14` placeholder**

```pine
// =========================================================
// ALERTS
// =========================================================
string sym = syminfo.tickerid
string tf  = timeframe.period

alertcondition(longCond,                  "Long entry signal",  message = "LONG entry {{ticker}} {{interval}} @ {{close}}")
alertcondition(shortCond,                 "Short entry signal", message = "SHORT entry {{ticker}} {{interval}} @ {{close}}")
alertcondition(chochUp,                   "CHoCH bull",         message = "CHoCH BULL {{ticker}} {{interval}} @ {{close}}")
alertcondition(chochDown,                 "CHoCH bear",         message = "CHoCH BEAR {{ticker}} {{interval}} @ {{close}}")

// Position-close alert — fires whenever the strategy closes a position
bool justClosedLong  = strategy.position_size == 0 and strategy.position_size[1] > 0
bool justClosedShort = strategy.position_size == 0 and strategy.position_size[1] < 0
alertcondition(justClosedLong  or justClosedShort, "Position closed",  message = "EXIT {{ticker}} {{interval}} @ {{close}}")
```

(5 conditions total, matching spec §8. Combined exit alert because the same strategy can't fire long-only or short-only exit alerts without separate tracking — single "Position closed" alert covers both cases.)

- [ ] **Step 2: Compile, save, local backup, commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: alerts (long/short entry, position close, CHoCH bull/bear)"
```

---

## Task 15: Visual layer (leg lines, zone box, custom entry/exit markers)

**Files:**
- Modify: `D:\trade-agent\pinescript\smc-kao-resumption-strategy.pine`

- [ ] **Step 1: Add visual-toggle inputs**

```pine
inputShowLeg  = input.bool(true, "Show legHigh/legLow lines", group = "Visuals")
inputShowMid  = input.bool(true, "Show legMid (50%) line",   group = "Visuals")
inputShowZone = input.bool(true, "Show discount/premium zone box", group = "Visuals")
inputShowMarks = input.bool(true, "Show entry/exit markers", group = "Visuals")
```

- [ ] **Step 2: Replace `// Visual layer — Task 15` placeholder**

```pine
// =========================================================
// VISUAL LAYER
// =========================================================
plot(inputShowLeg  and not na(legHigh) ? legHigh : na, "Leg High", color = color.new(color.green, 50), linewidth = 1, style = plot.style_linebr)
plot(inputShowLeg  and not na(legLow)  ? legLow  : na, "Leg Low",  color = color.new(color.red,   50), linewidth = 1, style = plot.style_linebr)
plot(inputShowMid  and not na(legMid)  ? legMid  : na, "Leg Mid",  color = color.new(color.gray,  30), linewidth = 1, style = plot.style_linebr)

// Discount / Premium zone box — drawn fresh every bar (simple bg fill)
color zoneColor = trendDir == 1 ? color.new(color.green, 92) : trendDir == -1 ? color.new(color.red, 92) : na
float zoneTop    = trendDir == 1 ? legMid  : legHigh
float zoneBottom = trendDir == 1 ? legLow  : legMid
bgcolor(inputShowZone and trendDir != 0 and close >= zoneBottom and close <= zoneTop ? zoneColor : na, title = "Discount/Premium Zone")

// Entry/exit markers (replacing the placeholder triangles from Task 9)
plotshape(inputShowMarks and longCond,                                                              title="Long Entry",  location=location.belowbar, style=shape.triangleup,   color=color.new(color.lime,   0), size=size.small,  text="L")
plotshape(inputShowMarks and shortCond,                                                             title="Short Entry", location=location.abovebar, style=shape.triangledown, color=color.new(color.red,    0), size=size.small,  text="S")
plotshape(inputShowMarks and (justClosedLong or justClosedShort),                                   title="Exit",        location=location.absolute, style=shape.xcross,       color=color.new(color.yellow, 0), size=size.tiny)
```

**Note:** the existing `plotshape` calls from Task 9 (without `inputShowMarks` gate) should be **removed** to avoid duplicate markers. Find and delete those two lines.

- [ ] **Step 3: Compile, save, local backup, commit**

```bash
cd D:/trade-agent && git add pinescript/smc-kao-resumption-strategy.pine && git commit -m "feat: visual layer (leg lines, mid, zone bgcolor, entry/exit markers)"
```

---

## Task 16: 6-symbol H1 + H4 sweep

**Files:**
- Create: `D:\trade-agent\docs\superpowers\plans\artifacts\2026-05-21-symbol-sweep.md`

- [ ] **Step 1: Run backtests on each symbol/TF combo via batch_run**

```
mcp__tradingview__batch_run(
    symbols=["FX:EURUSD","FX:GBPJPY","FX:GBPUSD","FX:USDJPY","FX:EURJPY","TICKMILL:XAUUSD"],
    timeframes=["60","240"],
    action="capture_strategy_metrics"
)
```

(If `batch_run` doesn't expose a `capture_strategy_metrics` action, fall back to: for each combo, `chart_set_symbol` + `chart_set_timeframe` + `data_get_strategy_results` + record.)

- [ ] **Step 2: Tabulate results**

Write `D:\trade-agent\docs\superpowers\plans\artifacts\2026-05-21-symbol-sweep.md`:

```markdown
# SMC KAO Resumption Strategy — 6-Symbol Sweep (2026-05-21)

Run on `SMC KAO Resumption Strategy v1.0` with default inputs (risk 1%, both directions, defaults for re-arm).

| Symbol | TF | Trades | PF | Win % | Max DD % | Avg R |
|---|---|---|---|---|---|---|
| EURUSD | H1 | ... | ... | ... | ... | ... |
| EURUSD | H4 | ... | ... | ... | ... | ... |
| GBPJPY | H1 | ... |
| ... | ... |
| XAUUSD | H4 | ... |

## Informal baseline
- Target: PF > 1.3 on ≥ 4/6 symbols (one of the two TFs counts)
- Outcome: [PASS / TUNE]

## Next steps
- If TUNE: try pivot-length sensitivity, KBB bandwidth, min-bars-in-trend gate
- If PASS: ship as v1.0, plan v2 features (HTF filter, etc.)
```

- [ ] **Step 3: Restore chart to original state**

```
mcp__tradingview__chart_set_symbol(symbol="TICKMILL:EURUSD")
mcp__tradingview__chart_set_timeframe(timeframe="60")
```

- [ ] **Step 4: Commit sweep artifact**

```bash
cd D:/trade-agent && git add docs/superpowers/plans/artifacts/2026-05-21-symbol-sweep.md && git commit -m "chore: 6-symbol H1+H4 backtest sweep results for resumption strategy v1.0"
```

- [ ] **Step 5: Push to GitHub**

Per Daniel's standing preference (push after significant work):

```bash
cd D:/trade-agent && git push origin master
```

If push is rejected because of remote changes: `git pull --rebase origin master`, resolve, re-push.

---

## Self-review

**Spec coverage check** — every section of the spec maps to a task:

| Spec section | Task(s) |
|---|---|
| §2 State machine | Task 7, verified Task 8 |
| §3 Entry triggers | Task 9, verified Task 10 |
| §4 Exit logic | Task 11, verified Task 13 |
| §5 Position sizing | Task 12 |
| §6 Inputs | Tasks 3, 5, 7, 9, 11, 12, 15 (added incrementally) |
| §7 Plots | Task 7 (diagnostic) + Task 15 (visuals) + Task 5 (KBB plots) |
| §8 Alerts | Task 14 |
| §9 File & naming | Task 3 |
| §10 Build sequence | Tasks 1–15 |
| §11 Verification protocol | Tasks 4, 6, 8, 10, 13, 16 |

**Placeholder scan** — there are deliberate `<KAO_chochUp>` / `<KAO_chochDown>` / `<KAO_pivotLowPrice>` etc. substitution slots in Tasks 7 and 11. These are NOT plan-failure placeholders; they're explicit substitution points with grep instructions to find the actual KAO variable names. The plan tells the executing agent exactly how to resolve them (Step 1 of each affected task). Acceptable.

**Type consistency check** — `chochUp`/`chochDown` declared in Task 7 Step 2, referenced in Task 11 Step 2 and Task 14. `trailSL`/`frozenSL`/`entryPrice` declared in Task 11, referenced in Task 12. `legHigh`/`legLow`/`legMid`/`armed`/`barsInTrend` declared in Task 7, referenced in Task 9. Consistent.

**Open notes for executing agent:**
- `kbb_basis`/`kbb_upper`/`kbb_lower` names in Task 5 Step 2 must match whatever the executing agent settles on — keep them stable across Tasks 7, 9, 11.
- KAO pivot variables (`<KAO_pivotLow*>` etc.) must be **the same variable** referenced in Tasks 7 (CHoCH detection) and 11 (trail SL pivots) — find them once in Task 7 Step 1, reuse in Task 11 Step 2.
