# Playbook System

> The core execution engine of Trade Agent. Playbooks are multi-phase state machines that execute trading strategies deterministically at runtime with zero AI calls. AI is only used at build time to transform natural language into the playbook JSON structure.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Playbook JSON Schema](#2-playbook-json-schema)
3. [Expression Language](#3-expression-language)
4. [Phase Design Patterns](#4-phase-design-patterns)
5. [Position Management](#5-position-management)
6. [Indicator Skills System](#6-indicator-skills-system)
7. [Trade Journal](#7-trade-journal)
8. [AI-Assisted Refinement](#8-ai-assisted-refinement)
9. [Runtime Execution Flow](#9-runtime-execution-flow)
10. [Complete Example: SMC OTE Playbook](#10-complete-example-smc-ote-playbook)

---

## 1. Overview

A playbook is a fully self-contained trading strategy encoded as a finite state machine. It defines a set of **phases**, each with conditions for **transitioning** to other phases, **actions** to execute on transition (open trade, set variables, log), and **position management rules** for active trades.

The critical architectural insight is the separation of concerns between AI and execution:

- **Build time (AI):** The user describes a strategy in natural language. Claude parses the description, loads relevant indicator skills files, and produces a complete playbook JSON config. This is the only point where AI is invoked.
- **Runtime (deterministic):** The PlaybookEngine evaluates the playbook on every bar close using a safe expression evaluator. No network calls, no AI inference, no latency. Pure state-machine logic driven by indicator values and price.

### Comparison: Legacy Strategy Engine vs. Playbook Engine

| Feature | Legacy Strategy Engine | Playbook Engine |
|---|---|---|
| Condition structure | 4 flat groups (entry_long, exit_long, entry_short, exit_short) | Multi-phase state machine with arbitrary topology |
| SL/TP | Fixed values or none | Dynamic expressions evaluated at runtime |
| Position management | None | Breakeven, trailing stop, partial close, dynamic SL/TP modification |
| State tracking | None | Typed variables persisted across phases |
| Timeouts | None | Per-phase bar timeouts with auto-transition |
| AI at runtime | Optional signal explanation via Claude Sonnet | Zero AI calls |
| Re-entry logic | Not supported | Multi-leg re-entry via phase cycles |
| Bidirectional trading | Separate long/short condition groups | Separate phase paths for each direction |
| Condition evaluation | Filter/trigger classification with cross detection | Arbitrary expression comparison with full arithmetic |

### Key Source Files

| File | Purpose |
|---|---|
| `agent/models/playbook.py` | Pydantic models for the playbook JSON schema |
| `agent/playbook_engine.py` | Runtime state machine runner |
| `agent/playbook_eval.py` | Safe AST-based expression evaluator |
| `agent/ai_service.py` | AI-powered playbook builder and refiner |
| `agent/journal_writer.py` | Trade context capture for every position |
| `agent/models/journal.py` | Journal entry and market context models |
| `agent/api/playbooks.py` | REST API routes for playbook CRUD and refinement |
| `agent/prompts/playbook_builder.md` | System prompt for the AI builder |
| `agent/prompts/playbook_refiner.md` | System prompt for the AI refiner |
| `agent/indicators/skills/*.md` | Per-indicator knowledge files loaded during build |

---

## 2. Playbook JSON Schema

Schema version: `playbook-v1`

### Top-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `$schema` | string | Yes | Always `"playbook-v1"` |
| `id` | string | Yes | Kebab-case identifier (e.g., `"smc-ote-gold-swing"`) |
| `name` | string | Yes | Human-readable name |
| `description` | string | No | What the strategy does |
| `symbols` | string[] | No | Target symbols. Default: `["XAUUSD"]` |
| `autonomy` | enum | No | `"signal_only"` (default), `"semi_auto"`, or `"full_auto"` |
| `indicators` | IndicatorConfig[] | Yes | All indicators the playbook uses |
| `variables` | dict[string, PlaybookVariable] | No | Variables tracked across phases |
| `phases` | dict[string, Phase] | Yes | Named phases forming the state machine |
| `initial_phase` | string | No | Starting phase name. Default: `"idle"` |
| `risk` | RiskConfig | No | Risk parameters |

### IndicatorConfig

```json
{
  "id": "h4_rsi",
  "name": "RSI",
  "timeframe": "H4",
  "params": {"period": 14}
}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier. Convention: `{timeframe_lower}_{indicator_lower}` or `{timeframe_lower}_{indicator_lower}{param}`. Examples: `h4_rsi`, `m15_ema20`, `h4_smc_structure` |
| `name` | string | Indicator name matching the catalog (e.g., `"RSI"`, `"EMA"`, `"SMC_Structure"`) |
| `timeframe` | string | Valid timeframes: `M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`, `W1` |
| `params` | dict | Indicator-specific parameters (e.g., `{"period": 14}`) |

### PlaybookVariable

```json
{
  "entry_price": {"type": "float", "default": 0.0},
  "trade_count": {"type": "int", "default": 0},
  "breakeven_hit": {"type": "bool", "default": false}
}
```

| Field | Type | Description |
|---|---|---|
| `type` | enum | `"float"`, `"int"`, `"bool"`, or `"string"` |
| `default` | any | Initial value when playbook starts or resets |

Variables persist across bar evaluations within a phase. They reset to defaults only when a playbook is first loaded. Phase transitions do NOT reset variables -- only the `transition_to()` method resets phase-level counters (`bars_in_phase`, `phase_timeframe_bars`, `fired_once_rules`).

### RiskConfig

```json
{
  "max_lot": 0.1,
  "max_daily_trades": 5,
  "max_drawdown_pct": 3.0,
  "max_open_positions": 2
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `max_lot` | float | 0.1 | Maximum lot size per trade |
| `max_daily_trades` | int | 5 | Maximum trades per day |
| `max_drawdown_pct` | float | 3.0 | Maximum drawdown percentage before pausing |
| `max_open_positions` | int | 2 | Maximum concurrent open positions |

### Phase

A single state in the state machine.

```json
{
  "description": "Wait for H4 bullish structure and RSI pullback",
  "evaluate_on": ["H4"],
  "transitions": [ ... ],
  "timeout": {"bars": 20, "timeframe": "H4", "to": "idle"},
  "position_management": [ ... ],
  "on_trade_closed": {"to": "idle"}
}
```

| Field | Type | Description |
|---|---|---|
| `description` | string | Human-readable explanation of what this phase does |
| `evaluate_on` | string[] | Which timeframe bar closes trigger evaluation of this phase. Example: `["H4", "M15"]` |
| `transitions` | Transition[] | Possible transitions out of this phase, checked in priority order (descending) |
| `timeout` | PhaseTimeout or null | Auto-transition after N bars with no transition firing |
| `position_management` | PositionManagementRule[] | Rules for managing an open position while in this phase |
| `on_trade_closed` | PhaseTransitionRef or null | Phase to transition to when the open trade closes (SL hit, TP hit, manual close) |

### PhaseTimeout

```json
{"bars": 20, "timeframe": "H4", "to": "idle"}
```

| Field | Type | Description |
|---|---|---|
| `bars` | int | Number of bar closes before timeout fires |
| `timeframe` | string | Which timeframe's bars to count |
| `to` | string | Target phase on timeout |

The engine tracks bar counts per timeframe within each phase via `state.phase_timeframe_bars`. When the count for the timeout's timeframe reaches or exceeds `bars`, the engine transitions to the `to` phase. Timeout is checked **before** transitions on each evaluation.

### Transition

```json
{
  "to": "wait_entry_long",
  "priority": 1,
  "conditions": {
    "type": "AND",
    "rules": [
      {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish market structure"},
      {"left": "ind.h4_rsi.value", "operator": "<", "right": "50", "description": "RSI below 50 — room to run"}
    ]
  },
  "actions": [
    {"set_var": "structure_high", "expr": "ind.h4_smc_structure.ref_high"},
    {"log": "Bullish setup detected on H4"}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `to` | string | Target phase name |
| `priority` | int | Higher values are checked first. Default: 0 |
| `conditions` | CheckCondition | Must evaluate to true for the transition to fire |
| `actions` | TransitionAction[] | Actions to execute when the transition fires |

Transitions are sorted by `priority` descending before evaluation. The first transition whose conditions evaluate to true fires, and no further transitions are checked for that evaluation cycle.

### CheckCondition

```json
{
  "type": "AND",
  "rules": [
    {"left": "ind.h4_rsi.value", "operator": "<", "right": "30", "description": "RSI oversold"},
    {"left": "ind.m15_stochastic.k", "operator": "<", "right": "20", "description": "Stochastic oversold"}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `type` | enum | `"AND"` (all rules must pass) or `"OR"` (any rule can pass) |
| `rules` | CheckRule[] | Array of individual rule checks |

If `rules` is empty, the condition evaluates to **false** (no vacuous truth).

### CheckRule

```json
{"left": "ind.h4_rsi.value", "operator": "<", "right": "30", "description": "RSI oversold"}
```

| Field | Type | Description |
|---|---|---|
| `left` | string | Expression string for the left operand (e.g., `"ind.h4_rsi.value"`, `"_price"`, `"var.initial_sl"`) |
| `operator` | string | Comparison operator: `"<"`, `">"`, `"<="`, `">="`, `"=="`, `"!="` |
| `right` | string | Expression string for the right operand. Can be a numeric literal as a string (e.g., `"30"`) or another expression (e.g., `"ind.h4_ema20.value"`) |
| `description` | string | Human-readable explanation of the rule |

Both `left` and `right` are evaluated through the expression evaluator before comparison. This means `"right": "30"` is parsed as the numeric literal 30, and `"right": "ind.h4_ema20.value"` is resolved to that indicator's current value.

### TransitionAction

Each action object should have exactly one of the following action fields set:

```json
// Set a playbook variable to an expression result
{"set_var": "entry_price", "expr": "_price"}

// Open a trade with dynamic SL/TP
{"open_trade": {
  "direction": "BUY",
  "lot": {"expr": "risk.max_lot"},
  "sl": {"expr": "ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5"},
  "tp": {"expr": "_price + (_price - var.initial_sl) * 3"}
}}

// Close the currently open trade
{"close_trade": true}

// Log a message
{"log": "Entry triggered — opening BUY position"}
```

| Field | Type | Description |
|---|---|---|
| `set_var` + `expr` | string, string | Set variable `set_var` to the evaluated result of `expr` |
| `open_trade` | TradeAction | Open a new trade |
| `close_trade` | bool | If true, close the currently open trade |
| `log` | string | Log a message (appears in engine logs) |

### TradeAction

| Field | Type | Description |
|---|---|---|
| `direction` | enum | `"BUY"` or `"SELL"` |
| `lot` | DynamicExpr or null | Lot size expression. Defaults to `risk.max_lot` if null |
| `sl` | DynamicExpr or null | Stop loss price expression |
| `tp` | DynamicExpr or null | Take profit price expression |

When a trade is opened, the engine automatically stores `initial_sl` and `initial_tp` in the playbook's variables for use in position management expressions. After the trade executor confirms the fill, `open_price`, `lot`, `sl`, and `tp` are stored in the state variables and become accessible via `trade.*` expressions.

### PositionManagementRule

Applied every evaluation cycle when the phase has an open position:

```json
{
  "name": "breakeven_at_1rr",
  "once": true,
  "continuous": false,
  "when": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl)", "description": "Price reached 1R profit"}
    ]
  },
  "modify_sl": {"expr": "trade.open_price + ind.h4_atr.value * 0.1"}
}
```

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique identifier for the rule |
| `once` | bool | If true, the rule fires only once per position. After firing, it is added to `fired_once_rules` in the state and skipped on subsequent evaluations |
| `continuous` | bool | If true, the rule is re-evaluated every bar (used for trailing stops) |
| `when` | CheckCondition | Condition that must be true for the rule to fire |

Each rule has exactly one action (one of the following):

| Action Field | Type | Description |
|---|---|---|
| `modify_sl` | ModifySLAction `{"expr": "..."}` | Set stop loss to the expression value |
| `modify_tp` | ModifySLAction `{"expr": "..."}` | Set take profit to the expression value |
| `trail_sl` | TrailSLAction `{"distance": {"expr": "..."}, "step": {"expr": "..."}}` | Trail stop loss by `distance`, moving in increments of `step` |
| `partial_close` | PartialCloseAction `{"pct": 50}` | Close `pct`% of the open position |

Rules that have `once: true` are skipped once they appear in `state.fired_once_rules`. The fired-once list resets when transitioning to a new phase.

---

## 3. Expression Language

The expression evaluator (`agent/playbook_eval.py`) provides a safe, deterministic way to compute values at runtime. It uses Python's `ast` module to parse expressions into an abstract syntax tree, then walks the tree recursively -- never calling `eval()` or `exec()`.

### References

| Prefix | Example | Resolves To |
|---|---|---|
| `ind.<id>.<field>` | `ind.h4_atr.value` | Current indicator value from the DataManager cache |
| `prev.<id>.<field>` | `prev.m15_rsi.value` | Previous bar's indicator value (stored after each evaluation) |
| `var.<name>` | `var.initial_sl` | Playbook variable from the current state |
| `_price` | `_price` | Current mid price: `(bid + ask) / 2` |
| `trade.<field>` | `trade.open_price` | Open position field (open_price, sl, tp, lot, pnl) |
| `risk.<field>` | `risk.max_lot` | Risk config field (max_lot, max_daily_trades, max_drawdown_pct, max_open_positions) |

### Arithmetic

Standard arithmetic operators are supported with normal operator precedence:

| Operator | Meaning |
|---|---|
| `+` | Addition |
| `-` | Subtraction (binary and unary) |
| `*` | Multiplication |
| `/` | Division |
| `( )` | Grouping |

Examples:
```
_price + ind.h4_atr.value * 1.5
ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5
_price + (_price - var.initial_sl) * 3
trade.open_price + (trade.open_price - var.initial_sl)
risk.max_lot * 0.5
-ind.h4_atr.value
```

### Resolution Process

1. The expression string is parsed via `ast.parse(expr, mode="eval")`
2. The resulting AST is walked recursively by `_eval_node()`
3. Numeric literals (`ast.Constant`) return their float value directly
4. Unary operators (`+`, `-`) are applied to their operand
5. Binary operators (`+`, `-`, `*`, `/`) evaluate left and right recursively, then apply the operation
6. Simple names (`ast.Name`, e.g., `_price`) are resolved via `ctx.resolve(name)`
7. Dotted names (`ast.Attribute`, e.g., `ind.h4_rsi.value`) are reconstructed into a dotted string and resolved via `ctx.resolve()`
8. The `ExpressionContext.resolve()` method dispatches based on the first segment of the dotted name

### Safety Guarantees

- **No `eval()` or `exec()`** -- all evaluation is through AST node inspection
- **Whitelist of allowed operations** -- only `Add`, `Sub`, `Mult`, `Div` are supported as binary ops. No bitwise, no boolean, no power, no modulo
- **Whitelist of allowed node types** -- only `Constant`, `UnaryOp`, `BinOp`, `Name`, and `Attribute` nodes are processed. Function calls, subscripts, comprehensions, lambdas, and all other node types raise `ValueError`
- **Division by zero** -- explicitly checked and raises `ValueError` with a descriptive message
- **Unknown references** -- any name that cannot be resolved raises `ValueError` with the unresolved name. Examples: `"Indicator 'h4_rsi' field 'missing_field' not found"`, `"Variable 'undefined_var' not found"`
- **All results are floats** -- every expression evaluation returns a Python `float`

### Comparison Operators (used in CheckRules)

| Operator String | Python Operator |
|---|---|
| `"<"` | `operator.lt` |
| `">"` | `operator.gt` |
| `"<="` | `operator.le` |
| `">="` | `operator.ge` |
| `"=="` | `operator.eq` |
| `"!="` | `operator.ne` |

Condition evaluation (`evaluate_condition`) takes a dict with `type` (AND/OR) and `rules`, evaluates each rule's `left` and `right` expressions, applies the comparison operator, and combines results:
- `"AND"` -- `all(results)` (all rules must pass)
- `"OR"` -- `any(results)` (at least one rule must pass)
- Empty rules list returns `False`

---

## 4. Phase Design Patterns

### Standard 4-Phase (Most Common)

The workhorse pattern for swing and position trading. Separates structure detection, entry timing, trade opening, and position management into distinct phases.

```
idle --> wait_entry --> entry_ready --> in_position --> (trade closed) --> idle
```

```json
{
  "phases": {
    "idle": {
      "description": "Wait for H4 structural setup",
      "evaluate_on": ["H4"],
      "transitions": [
        {
          "to": "wait_entry_long",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish structure"},
              {"left": "ind.h4_rsi.value", "operator": "<", "right": "50", "description": "RSI not overbought"}
            ]
          },
          "actions": [
            {"set_var": "structure_high", "expr": "ind.h4_smc_structure.ref_high"},
            {"set_var": "strong_low", "expr": "ind.h4_smc_structure.strong_low"},
            {"log": "Bullish structure detected on H4"}
          ]
        },
        {
          "to": "wait_entry_short",
          "priority": 0,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Bearish structure"},
              {"left": "ind.h4_rsi.value", "operator": ">", "right": "50", "description": "RSI not oversold"}
            ]
          },
          "actions": [
            {"set_var": "structure_low", "expr": "ind.h4_smc_structure.ref_low"},
            {"set_var": "strong_high", "expr": "ind.h4_smc_structure.strong_high"}
          ]
        }
      ]
    },
    "wait_entry_long": {
      "description": "Wait for M15 pullback into OTE zone",
      "evaluate_on": ["M15"],
      "transitions": [
        {
          "to": "in_position_long",
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "Price in OTE zone"},
              {"left": "_price", "operator": ">=", "right": "ind.h4_smc_structure.ote_bottom", "description": "Price above OTE bottom"},
              {"left": "ind.m15_rsi.value", "operator": "<", "right": "35", "description": "M15 RSI oversold"}
            ]
          },
          "actions": [
            {"set_var": "initial_sl", "expr": "var.strong_low - ind.h4_atr.value * 0.5"},
            {"open_trade": {
              "direction": "BUY",
              "lot": {"expr": "risk.max_lot"},
              "sl": {"expr": "var.strong_low - ind.h4_atr.value * 0.5"},
              "tp": {"expr": "_price + (_price - var.initial_sl) * 3"}
            }},
            {"log": "Long entry in OTE zone"}
          ]
        }
      ],
      "timeout": {"bars": 20, "timeframe": "M15", "to": "idle"}
    },
    "in_position_long": {
      "description": "Manage long position with breakeven and trailing",
      "evaluate_on": ["M15"],
      "transitions": [
        {
          "to": "idle",
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Structure turned bearish"}
            ]
          },
          "actions": [
            {"close_trade": true},
            {"log": "Closing long — structure reversal"}
          ]
        }
      ],
      "position_management": [
        {
          "name": "breakeven_at_1rr",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl)", "description": "Price reached 1R profit"}
            ]
          },
          "modify_sl": {"expr": "trade.open_price + ind.h4_atr.value * 0.1"}
        },
        {
          "name": "partial_close_2rr",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl) * 2", "description": "Price reached 2R profit"}
            ]
          },
          "partial_close": {"pct": 50}
        },
        {
          "name": "trail_after_2rr",
          "continuous": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl) * 2", "description": "Price past 2R"}
            ]
          },
          "trail_sl": {
            "distance": {"expr": "ind.h4_atr.value * 1.0"},
            "step": {"expr": "ind.h4_atr.value * 0.2"}
          }
        }
      ],
      "on_trade_closed": {"to": "idle"}
    }
  }
}
```

**When to use:** Most swing and position strategies. Any strategy that needs to differentiate between "looking for a setup" and "waiting for precise entry."

### Multi-Leg Re-Entry

Allows the playbook to re-enter a trade after the first position closes, without going all the way back to idle. Useful for trending markets where you want to catch multiple pullbacks within the same structural move.

```
idle --> wait --> entry --> in_position --> (closed) --> wait_reentry --> entry --> in_position --> idle
```

```json
{
  "phases": {
    "idle": {
      "description": "Wait for trend setup",
      "evaluate_on": ["H4"],
      "transitions": [
        {
          "to": "wait_pullback",
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish trend"}
            ]
          },
          "actions": [
            {"set_var": "leg_count", "expr": "0"}
          ]
        }
      ]
    },
    "wait_pullback": {
      "description": "Wait for pullback on M15",
      "evaluate_on": ["M15"],
      "transitions": [
        {
          "to": "in_position",
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "Price pulled back to OTE"},
              {"left": "ind.m15_rsi.value", "operator": "<", "right": "40", "description": "RSI shows pullback"}
            ]
          },
          "actions": [
            {"set_var": "leg_count", "expr": "var.leg_count + 1"},
            {"open_trade": {
              "direction": "BUY",
              "sl": {"expr": "ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.3"},
              "tp": {"expr": "ind.h4_smc_structure.ref_high + ind.h4_atr.value"}
            }}
          ]
        }
      ],
      "timeout": {"bars": 30, "timeframe": "M15", "to": "idle"}
    },
    "in_position": {
      "description": "Manage position",
      "evaluate_on": ["M15"],
      "transitions": [
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "!=", "right": "1", "description": "Trend invalidated"}
            ]
          },
          "actions": [
            {"close_trade": true}
          ]
        }
      ],
      "position_management": [
        {
          "name": "breakeven",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl)", "description": "1R reached"}
            ]
          },
          "modify_sl": {"expr": "trade.open_price + ind.h4_atr.value * 0.05"}
        }
      ],
      "on_trade_closed": {"to": "wait_reentry"}
    },
    "wait_reentry": {
      "description": "Check if re-entry is appropriate",
      "evaluate_on": ["H4"],
      "transitions": [
        {
          "to": "wait_pullback",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Trend still bullish"},
              {"left": "var.leg_count", "operator": "<", "right": "3", "description": "Less than 3 legs taken"}
            ]
          }
        },
        {
          "to": "idle",
          "priority": 0,
          "conditions": {
            "type": "OR",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "!=", "right": "1", "description": "Trend no longer bullish"},
              {"left": "var.leg_count", "operator": ">=", "right": "3", "description": "Max legs reached"}
            ]
          }
        }
      ],
      "timeout": {"bars": 5, "timeframe": "H4", "to": "idle"}
    }
  }
}
```

**When to use:** Trending strategies, swing trading with multiple entries, pyramiding approaches.

### Scalping (2-Phase)

Minimal overhead. Single timeframe, simple entry/exit, tight management. No intermediate "wait" phase -- the idle phase directly evaluates entry conditions.

```
idle --> in_position --> idle
```

```json
{
  "phases": {
    "idle": {
      "description": "Scan for scalp entry on M5",
      "evaluate_on": ["M5"],
      "transitions": [
        {
          "to": "in_position",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.m5_rsi.value", "operator": "<", "right": "25", "description": "RSI deeply oversold"},
              {"left": "ind.m5_bollinger.percent_b", "operator": "<", "right": "0.05", "description": "Price at lower Bollinger band"}
            ]
          },
          "actions": [
            {"open_trade": {
              "direction": "BUY",
              "sl": {"expr": "_price - ind.m5_atr.value * 1.5"},
              "tp": {"expr": "_price + ind.m5_atr.value * 2.0"}
            }}
          ]
        }
      ]
    },
    "in_position": {
      "description": "Quick exit management",
      "evaluate_on": ["M5"],
      "transitions": [
        {
          "to": "idle",
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.m5_rsi.value", "operator": ">", "right": "70", "description": "RSI overbought — take profit signal"}
            ]
          },
          "actions": [
            {"close_trade": true}
          ]
        }
      ],
      "position_management": [
        {
          "name": "quick_breakeven",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + ind.m5_atr.value * 0.5", "description": "Small profit buffer"}
            ]
          },
          "modify_sl": {"expr": "trade.open_price + ind.m5_atr.value * 0.1"}
        }
      ],
      "on_trade_closed": {"to": "idle"}
    }
  }
}
```

**When to use:** Fast-paced scalping, mean-reversion bounces, news spikes.

### Bidirectional

Separate phase paths for long and short setups, sharing a common idle phase. This is the recommended pattern for strategies that trade both directions.

```
                   +--> wait_entry_long  --> in_position_long  --+
                   |                                              |
idle ----+---------+                                              +---> idle
                   |                                              |
                   +--> wait_entry_short --> in_position_short --+
```

The idle phase has two transitions with different priorities. Long and short paths are completely independent, each with their own entry conditions, SL/TP calculations, and position management rules.

```json
{
  "phases": {
    "idle": {
      "evaluate_on": ["H4"],
      "transitions": [
        {
          "to": "wait_entry_long",
          "priority": 1,
          "conditions": {"type": "AND", "rules": [
            {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "Bullish bias"}
          ]}
        },
        {
          "to": "wait_entry_short",
          "priority": 0,
          "conditions": {"type": "AND", "rules": [
            {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "Bearish bias"}
          ]}
        }
      ]
    },
    "wait_entry_long": {
      "evaluate_on": ["M15"],
      "transitions": [
        {"to": "in_position_long", "conditions": {"type": "AND", "rules": [
          {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "In OTE zone"}
        ]},
        "actions": [
          {"open_trade": {"direction": "BUY", "sl": {"expr": "ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5"}, "tp": {"expr": "_price + ind.h4_atr.value * 4"}}}
        ]}
      ],
      "timeout": {"bars": 20, "timeframe": "M15", "to": "idle"}
    },
    "in_position_long": {
      "evaluate_on": ["M15"],
      "position_management": [],
      "on_trade_closed": {"to": "idle"}
    },
    "wait_entry_short": {
      "evaluate_on": ["M15"],
      "transitions": [
        {"to": "in_position_short", "conditions": {"type": "AND", "rules": [
          {"left": "_price", "operator": ">=", "right": "ind.h4_smc_structure.ote_bottom", "description": "In OTE zone (short)"}
        ]},
        "actions": [
          {"open_trade": {"direction": "SELL", "sl": {"expr": "ind.h4_smc_structure.strong_high + ind.h4_atr.value * 0.5"}, "tp": {"expr": "_price - ind.h4_atr.value * 4"}}}
        ]}
      ],
      "timeout": {"bars": 20, "timeframe": "M15", "to": "idle"}
    },
    "in_position_short": {
      "evaluate_on": ["M15"],
      "position_management": [],
      "on_trade_closed": {"to": "idle"}
    }
  }
}
```

**When to use:** Any strategy that should trade both directions. The builder prompt instructs Claude to default to this pattern.

---

## 5. Position Management

Position management rules fire during the `in_position` phase on every bar close evaluation when there is an open ticket. They provide mechanical, rule-based trade management with no human intervention required.

### Breakeven at 1R

Move the stop loss to entry price plus a small buffer when the unrealized profit reaches 1x the initial risk distance.

**How it works:**
- Risk distance = `open_price - initial_sl` (for longs)
- 1R target = `open_price + risk_distance`
- When `_price >= 1R target`, move SL to `open_price + small_buffer`
- The buffer (typically 0.1x ATR) prevents getting stopped out by spread noise at breakeven

```json
{
  "name": "breakeven_at_1rr",
  "once": true,
  "when": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl)", "description": "Price reached 1R profit"}
    ]
  },
  "modify_sl": {"expr": "trade.open_price + ind.h4_atr.value * 0.1"}
}
```

**Why `once: true`:** Breakeven should fire exactly once. After the SL is moved, we do not want to keep resetting it to breakeven on every bar.

### Partial Close at 2R

Close 50% of the position when price reaches 2x the initial risk distance. This locks in profit while letting the remainder run with a trailing stop.

```json
{
  "name": "partial_close_2rr",
  "once": true,
  "when": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl) * 2", "description": "Price reached 2R profit"}
    ]
  },
  "partial_close": {"pct": 50}
}
```

**Implementation detail:** The trade executor implements partial close by opening an opposite-direction order for the partial lot size (MT5 netting accounts do not support native partial close). The journal writer tracks the remaining lot size.

### Trailing Stop

After the position is sufficiently profitable, trail the stop loss behind the current price by an ATR-based distance. The trail only moves in the profitable direction -- it never moves the SL backward.

```json
{
  "name": "trail_after_breakeven",
  "continuous": true,
  "when": {
    "type": "AND",
    "rules": [
      {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl) * 2", "description": "Price past 2R — trail active"}
    ]
  },
  "trail_sl": {
    "distance": {"expr": "ind.h4_atr.value * 1.0"},
    "step": {"expr": "ind.h4_atr.value * 0.2"}
  }
}
```

| Parameter | Meaning |
|---|---|
| `distance` | How far behind the current price to place the trailing SL |
| `step` | Minimum price movement before the trail advances (prevents micro-adjustments) |

**Why `continuous: true`:** The trailing stop must re-evaluate on every bar to ratchet the SL up as price advances.

### Dynamic SL/TP

Use indicator values to compute SL/TP levels instead of fixed pip amounts. This adapts the trade to current market conditions.

```json
// SL below the structural strong low with ATR buffer
"sl": {"expr": "ind.h4_smc_structure.strong_low - ind.h4_atr.value * 0.5"}

// TP at 3:1 risk-reward ratio
"tp": {"expr": "_price + (_price - var.initial_sl) * 3"}

// TP at the next structural level
"tp": {"expr": "ind.h4_smc_structure.ref_high + ind.h4_atr.value * 0.5"}
```

**Best practice:** Always use ATR-based buffers when placing SL/TP near structural levels. Raw structural levels (like `strong_low`) are often hit by spread or volatility spikes. Adding `ATR * 0.3-0.5` as buffer significantly reduces false stops.

---

## 6. Indicator Skills System

The indicator skills system gives the AI deep, structured knowledge about each indicator during playbook building. Without skills, the AI knows indicator names and basic usage; with skills, it knows parameter tuning ranges, pattern recognition recipes, common pitfalls, and XAUUSD-specific configurations.

### How Skills are Loaded During Build

1. **Identify indicators from natural language.** The `_identify_indicators()` method in `AIService` scans the user's description for keyword matches. For example, "smart money structure" matches `SMC_Structure`, "RSI pullback" matches `RSI`.

2. **Always load `_combinations.md`.** This file contains cross-indicator combination knowledge -- which indicators work well together, which conflict, and recommended multi-indicator patterns.

3. **Always include ATR.** If any indicators are identified, ATR is always added to the set. ATR is essential for dynamic SL/TP sizing and volatility-aware position management.

4. **Load matching skills files.** For each identified indicator name, load `agent/indicators/skills/{Name}.md` if it exists. The content is concatenated with section headers.

5. **Inject into system prompt.** The loaded skills content is appended to the `playbook_builder.md` system prompt along with the indicator catalog JSON. Claude then has:
   - The playbook JSON schema and design patterns (from `playbook_builder.md`)
   - The full indicator catalog with available names, parameters, and output fields
   - Deep indicator expertise from the relevant skills files
   - Cross-indicator combination knowledge

### Skills File Structure

Each skills file (`agent/indicators/skills/{Name}.md`) follows a consistent structure:

1. **Overview** -- What the indicator measures, output fields and their types
2. **When to Use** -- Strategic contexts where this indicator excels
3. **Parameters Guide** -- Parameter ranges with recommended values and what each controls
4. **Patterns** -- Specific setups with complete playbook JSON examples showing conditions, actions, and management rules
5. **Combinations** -- Which other indicators pair well and why
6. **Pitfalls** -- Common mistakes, false signal scenarios, and how to avoid them
7. **XAUUSD-Specific Tuning** -- Parameter adjustments specific to gold's volatility and session behavior

### Available Skills Files

| Skill File | Indicator |
|---|---|
| `RSI.md` | Relative Strength Index |
| `EMA.md` | Exponential Moving Average |
| `SMA.md` | Simple Moving Average |
| `MACD.md` | Moving Average Convergence Divergence |
| `Stochastic.md` | Stochastic Oscillator |
| `Bollinger.md` | Bollinger Bands |
| `ATR.md` | Average True Range |
| `ADX.md` | Average Directional Index |
| `CCI.md` | Commodity Channel Index |
| `WilliamsR.md` | Williams %R |
| `SMC_Structure.md` | Smart Money Concepts: Market Structure |
| `OB_FVG.md` | Order Blocks and Fair Value Gaps |
| `NW_Envelope.md` | Nadaraya-Watson Kernel Regression Envelope |
| `_combinations.md` | Cross-indicator combination guide |
| `_template.md` | Template for creating new skills files |

### Keyword Matching

The `_identify_indicators()` method maps natural language keywords to skills file names:

| Skills File | Matched Keywords |
|---|---|
| `RSI` | rsi, relative strength |
| `EMA` | ema, exponential moving average, exponential ma |
| `SMA` | sma, simple moving average, simple ma, moving average |
| `MACD` | macd, moving average convergence |
| `Stochastic` | stochastic, stoch |
| `Bollinger` | bollinger, bb, boll |
| `ATR` | atr, average true range |
| `ADX` | adx, average directional, directional index |
| `CCI` | cci, commodity channel |
| `WilliamsR` | williams, williams %r, williams r, will%r |
| `SMC_Structure` | smc, smart money, market structure, bos, choch, break of structure, change of character, ote, optimal trade entry |
| `OB_FVG` | order block, fair value gap, ob, fvg, supply zone, demand zone, breaker |
| `NW_Envelope` | nadaraya, nw envelope, kernel regression, envelope |

---

## 7. Trade Journal

The journal system (`agent/journal_writer.py`) captures comprehensive context for every trade, creating a rich dataset for performance analysis and AI-assisted refinement.

### What Gets Captured

#### At Trade Entry (`on_trade_opened`)

| Data | Source | Description |
|---|---|---|
| **Entry indicator snapshot** | DataManager cache | All indicator values for every configured indicator at the moment of entry |
| **Market context** | DataManager + heuristics | ATR value and timeframe, trading session (asian/london/overlap/newyork), volatility level, trend direction, spread |
| **Playbook context** | PlaybookEngine state | Current phase name, all variable values at entry |
| **Entry conditions** | Signal conditions_snapshot | The specific transition conditions that fired to open the trade |
| **Trade details** | TradeAction | Symbol, direction, lot size, open price, initial SL, initial TP |
| **Tick data** | DataManager | Bid, ask, and spread at entry |

#### During Position (`on_management_event`)

Every management event is timestamped and appended to the journal entry:

| Field | Description |
|---|---|
| `time` | When the event occurred |
| `rule_name` | Which management rule fired (e.g., `"breakeven_at_1rr"`) |
| `action` | Action type: `"modify_sl"`, `"modify_tp"`, `"trail_sl"`, `"partial_close"` |
| `details` | Action-specific data (e.g., `{"old_sl": 2710.5, "new_sl": 2715.0}`) |
| `phase` | Playbook phase when the event occurred |

For partial closes, the journal also updates `lot_remaining` to track the reduced position size.

#### At Trade Exit (`on_trade_closed`)

| Data | Description |
|---|---|
| **Exit indicator snapshot** | All indicator values at the moment of exit |
| **Close price** | Actual fill price |
| **PnL** | Profit/loss in account currency |
| **PnL (pips)** | Profit/loss in pips, computed using symbol-specific pip values |
| **R:R achieved** | Actual risk-reward ratio: `reward / risk`. Negative for losses |
| **Outcome** | `"win"`, `"loss"`, or `"breakeven"` based on PnL |
| **Exit reason** | Why the trade closed |
| **Duration** | Time elapsed in seconds from open to close |
| **Final SL/TP** | The SL and TP values at the time of close (may differ from initial after management) |
| **Lot remaining** | 0 for full close, reduced amount for partial close |

### Exit Reasons

| Reason | Description |
|---|---|
| `tp_hit` | Price reached the take-profit level |
| `sl_hit` | Price reached the stop-loss level |
| `manual` | User manually closed the position |
| `signal_exit` | A playbook transition fired a `close_trade` action |
| `structure_reversal` | Market structure changed direction (detected by playbook conditions) |
| `timeout` | Phase timeout expired while in position |
| `kill_switch` | Emergency kill switch was activated |

### Computed Metrics

| Metric | Formula |
|---|---|
| PnL (pips) | `(close_price - open_price) / pip_size` (negated for SELL) |
| R:R achieved | `abs(close_price - open_price) / abs(open_price - sl_initial)` (negated for losses) |
| Duration | `close_time - open_time` in seconds |

### Market Context Capture

The `_capture_market_context()` method captures ambient market conditions:

- **Session detection** by UTC hour: Asian (0-8), London (8-12), Overlap (12-16), New York (16-21)
- **Trend** from SMC_Structure indicator if available on H4/H1/D1
- **ATR** from the highest available timeframe (H1 > H4 > M15)
- **Spread** from the latest tick

---

## 8. AI-Assisted Refinement

The refinement system creates a feedback loop between trade performance data and playbook configuration. It uses Claude Sonnet (not Opus) for cost efficiency, since refinement is conversational and iterative.

### Refine Flow

1. **User initiates refinement.** `POST /api/playbooks/:id/refine` with a `messages` array containing the conversation history.

2. **System gathers context.** The API route collects:
   - **Current playbook config** -- the full JSON being refined
   - **Journal analytics** -- aggregate stats (win rate, average PnL, average R:R, exit reason distribution) computed from `db.get_journal_analytics()`
   - **Per-condition win rates** -- how each individual condition rule performs, from `db.get_journal_condition_analytics()`
   - **Recent trade samples** -- the last 20 journal entries with full indicator snapshots, limited to 10 in the prompt to manage token count

3. **Skills injection.** The system identifies which indicators the playbook uses and loads their skills files, giving the refiner model deep knowledge about the indicators being discussed.

4. **Prompt assembly.** The `refine_playbook()` method in `AIService` builds the system prompt by concatenating:
   - `playbook_refiner.md` (the base refiner prompt with analysis framework)
   - Current playbook JSON
   - Journal analytics JSON
   - Per-condition win rates JSON
   - Recent trade samples JSON
   - Indicator skills content

5. **Claude Sonnet analyzes.** The model receives the full context and the user's conversation messages. It follows the analysis framework from the refiner prompt:
   - Win rate analysis (overall and per-condition)
   - Exit reason analysis (SL hits, timeouts, TP hits)
   - Per-condition performance (identify strong/weak signals)
   - Management event analysis (breakeven, trailing, partial close effectiveness)
   - Entry timing analysis (compare entry vs exit indicator values)

6. **Auto-update detection.** If Claude's response includes `<playbook_update>...</playbook_update>` tags containing a complete playbook JSON, the system:
   - Parses the JSON into a `PlaybookConfig`
   - Saves it to the database via `db.update_playbook()`
   - Returns `"updated": true` and the new config in the API response

7. **Engine hot-reload.** If the playbook is currently enabled and loaded in the engine, the system:
   - Unloads the old version via `engine.unload_playbook()`
   - Loads the updated version via `engine.load_playbook()`
   - The engine continues evaluation on the next bar close with the new config

### What the Refiner Can Change

- Condition thresholds (e.g., RSI < 30 changed to RSI < 25)
- Phase timeout values
- Position management parameters (breakeven level, trail distance, partial close percentage)
- Add or remove conditions within existing phases
- Modify SL/TP expressions
- Add or remove indicators
- Modify variable defaults

### What the Refiner Should NOT Change

- Overall strategy architecture (number of phases, flow direction)
- Symbol list (unless the user requests it)
- Autonomy level (unless the user requests it)
- Playbook ID

### Refinement Guidelines

The refiner prompt instructs Claude to:
- Be specific: "Change RSI threshold from 30 to 25" rather than "adjust RSI"
- Reference actual data: "RSI < 30 entries win 40% but RSI < 25 entries win 68%"
- Suggest one change at a time for proper A/B testing
- Always explain the expected impact of each change
- Consider XAUUSD-specific characteristics (high volatility, session-dependent behavior, institutional structure)
- Err on the side of conservative changes when uncertain

---

## 9. Runtime Execution Flow

This section describes exactly what happens on each bar close event, step by step.

### Event Chain

```
MT5 EA (MQL5)
  --> ZeroMQ PUB socket (port 5556)
    --> ZMQBridge.on_tick()
      --> DataManager.on_tick()
        --> DataManager._check_new_bar()
          --> bar_close_callbacks
            --> PlaybookEngine.evaluate_on_bar_close(symbol, timeframe)
```

### Step-by-Step Evaluation

**1. DataManager detects a new bar.**

`DataManager._check_new_bar()` compares the latest bar's timestamp against `_last_bar_time[(symbol, timeframe)]`. If the timestamp is newer, a new bar has closed. The DataManager fires all registered `_bar_close_callbacks`.

**2. PlaybookEngine.evaluate_on_bar_close(symbol, timeframe) is called.**

The engine iterates over all loaded playbook instances.

**3. For each enabled playbook matching the symbol:**

**3a. Check if timeframe is in phase.evaluate_on.**

If the current phase's `evaluate_on` list does not include this timeframe, skip this playbook for this bar close. This is how multi-timeframe playbooks work -- the idle phase might only evaluate on H4 bar closes, while the wait_entry phase evaluates on M15 bar closes.

**3b. Refresh indicators for this timeframe.**

For every indicator in the playbook config that matches this timeframe, call `DataManager.fetch_indicator()` to get the latest value from MT5 via ZeroMQ. This updates the DataManager cache.

**3c. Build ExpressionContext.**

Collect current indicator values from the DataManager cache into a flat dict (`{indicator_id: {field: value}}`). Collect previous indicator values from the engine's `_prev_indicators` store. Get the current mid price from the latest tick. If a position is open, build trade data from state variables. Construct the `ExpressionContext` with all of this data.

**3d. Increment bar counters.**

- `state.bars_in_phase += 1` (total bars regardless of timeframe)
- `state.phase_timeframe_bars[timeframe] += 1` (bars for this specific timeframe)

**3e. Check phase timeout.**

If the phase has a `timeout` configured, check if `phase_timeframe_bars[timeout.timeframe] >= timeout.bars`. If yes:
- Log the timeout event
- Call `instance.transition_to(timeout.to)` which resets `bars_in_phase`, `phase_timeframe_bars`, and `fired_once_rules`
- Persist state and return (no further evaluation this cycle)

**3f. Evaluate transitions in priority order.**

Sort the phase's transitions by `priority` descending. For each transition:
- Evaluate `transition.conditions` using `evaluate_condition()` which:
  - Iterates over all rules
  - Evaluates `left` and `right` expressions via `evaluate_expr()`
  - Applies the comparison operator
  - Combines results with AND/OR logic
- If the condition evaluates to `True`:
  - Execute all transition actions (set_var, open_trade, close_trade, log)
  - Call `instance.transition_to(transition.to)`
  - Persist state and return (first matching transition wins)

**3g. If transition fires: execute actions.**

Actions are processed sequentially:
- `set_var` + `expr`: Evaluate the expression and store the result in the playbook variable
- `open_trade`: Evaluate lot/sl/tp expressions, store initial_sl and initial_tp in variables, create a Signal object, emit to signal and trade action callbacks
- `close_trade`: Emit exit signal for the open position
- `log`: Write to the engine log

**3h. If in_position: evaluate position management rules.**

Only evaluated if the phase has `position_management` rules AND `state.open_ticket` is set (position is open). For each rule:
- Skip if `once: true` and `rule.name` is in `fired_once_rules`
- Evaluate the `when` condition
- If true, execute the action (modify_sl, modify_tp, trail_sl, partial_close) by emitting a management event through callbacks
- If `once: true`, add `rule.name` to `fired_once_rules`

**3i. Update previous indicator values.**

Store the current indicator values dict as the previous values for the next evaluation cycle. This makes `prev.*` references work.

**3j. Persist state to DB.**

Fire all `_state_change_callbacks` with the updated `PlaybookState`. The state contains: `current_phase`, `variables`, `bars_in_phase`, `phase_timeframe_bars`, `fired_once_rules`, `open_ticket`, `open_direction`.

### Trade Lifecycle Notifications

The PlaybookEngine exposes two notification methods called by the trade executor:

- `notify_trade_opened(playbook_id, ticket, direction, open_price, sl, tp, lot)` -- Sets `state.open_ticket`, `state.open_direction`, and stores open_price/lot/sl/tp in state variables. This makes `trade.*` expressions work in management rules.

- `notify_trade_closed(playbook_id)` -- Clears `state.open_ticket` and `state.open_direction`. If the current phase has `on_trade_closed`, transitions to the specified phase.

---

## 10. Complete Example: SMC OTE Playbook

This is a complete, production-ready playbook implementing a Smart Money Concepts Optimal Trade Entry strategy on XAUUSD. It uses H4 structure for directional bias and M15 for entry timing.

```json
{
  "$schema": "playbook-v1",
  "id": "smc-ote-gold-swing",
  "name": "SMC OTE Gold Swing",
  "description": "Smart Money Concepts swing strategy. Uses H4 market structure for directional bias (BOS/CHOCH), waits for M15 pullback into the OTE zone (61.8-78.6% retracement), and enters with RSI confirmation. Position management includes breakeven at 1R, partial close at 2R, and ATR trailing stop.",
  "symbols": ["XAUUSD"],
  "autonomy": "signal_only",
  "indicators": [
    {"id": "h4_smc_structure", "name": "SMC_Structure", "timeframe": "H4", "params": {"swing_length": 10}},
    {"id": "h4_rsi", "name": "RSI", "timeframe": "H4", "params": {"period": 14}},
    {"id": "h4_atr", "name": "ATR", "timeframe": "H4", "params": {"period": 14}},
    {"id": "m15_rsi", "name": "RSI", "timeframe": "M15", "params": {"period": 14}},
    {"id": "m15_smc_structure", "name": "SMC_Structure", "timeframe": "M15", "params": {"swing_length": 5}}
  ],
  "variables": {
    "structure_high": {"type": "float", "default": 0.0},
    "structure_low": {"type": "float", "default": 0.0},
    "strong_low": {"type": "float", "default": 0.0},
    "strong_high": {"type": "float", "default": 0.0},
    "initial_sl": {"type": "float", "default": 0.0},
    "initial_tp": {"type": "float", "default": 0.0},
    "entry_price": {"type": "float", "default": 0.0}
  },
  "phases": {
    "idle": {
      "description": "Scan H4 for bullish or bearish market structure with SMC",
      "evaluate_on": ["H4"],
      "transitions": [
        {
          "to": "wait_entry_long",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "H4 bullish market structure (BOS up or CHOCH to bullish)"},
              {"left": "ind.h4_rsi.value", "operator": "<", "right": "60", "description": "H4 RSI below 60 — not overbought, room for upside"},
              {"left": "ind.h4_atr.value", "operator": ">", "right": "2.0", "description": "Minimum ATR threshold — avoid dead market"}
            ]
          },
          "actions": [
            {"set_var": "structure_high", "expr": "ind.h4_smc_structure.ref_high"},
            {"set_var": "strong_low", "expr": "ind.h4_smc_structure.strong_low"},
            {"log": "H4 bullish structure detected — waiting for OTE pullback on M15"}
          ]
        },
        {
          "to": "wait_entry_short",
          "priority": 0,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "H4 bearish market structure (BOS down or CHOCH to bearish)"},
              {"left": "ind.h4_rsi.value", "operator": ">", "right": "40", "description": "H4 RSI above 40 — not oversold, room for downside"},
              {"left": "ind.h4_atr.value", "operator": ">", "right": "2.0", "description": "Minimum ATR threshold"}
            ]
          },
          "actions": [
            {"set_var": "structure_low", "expr": "ind.h4_smc_structure.ref_low"},
            {"set_var": "strong_high", "expr": "ind.h4_smc_structure.strong_high"},
            {"log": "H4 bearish structure detected — waiting for OTE pullback on M15"}
          ]
        }
      ]
    },
    "wait_entry_long": {
      "description": "Wait for M15 price to pull back into the H4 OTE zone (61.8-78.6% Fibonacci retracement) with RSI confirmation",
      "evaluate_on": ["M15"],
      "transitions": [
        {
          "to": "in_position_long",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "Price at or below OTE top (61.8% retracement)"},
              {"left": "_price", "operator": ">=", "right": "ind.h4_smc_structure.ote_bottom", "description": "Price at or above OTE bottom (78.6% retracement)"},
              {"left": "ind.m15_rsi.value", "operator": "<", "right": "35", "description": "M15 RSI oversold — momentum exhaustion on pullback"},
              {"left": "_price", "operator": ">", "right": "var.strong_low", "description": "Price still above protected low — structure intact"}
            ]
          },
          "actions": [
            {"set_var": "entry_price", "expr": "_price"},
            {"set_var": "initial_sl", "expr": "var.strong_low - ind.h4_atr.value * 0.5"},
            {"set_var": "initial_tp", "expr": "_price + (_price - var.initial_sl) * 3"},
            {"open_trade": {
              "direction": "BUY",
              "lot": {"expr": "risk.max_lot"},
              "sl": {"expr": "var.strong_low - ind.h4_atr.value * 0.5"},
              "tp": {"expr": "_price + (_price - var.initial_sl) * 3"}
            }},
            {"log": "LONG entry in OTE zone — SL below strong low, TP at 3R"}
          ]
        },
        {
          "to": "idle",
          "priority": 0,
          "conditions": {
            "type": "OR",
            "rules": [
              {"left": "_price", "operator": "<", "right": "var.strong_low", "description": "Price broke below strong low — bullish structure invalidated"},
              {"left": "ind.h4_smc_structure.trend", "operator": "!=", "right": "1", "description": "H4 structure no longer bullish"}
            ]
          },
          "actions": [
            {"log": "Long setup invalidated — returning to idle"}
          ]
        }
      ],
      "timeout": {"bars": 30, "timeframe": "M15", "to": "idle"}
    },
    "wait_entry_short": {
      "description": "Wait for M15 price to rally into the H4 OTE zone with RSI confirmation for shorts",
      "evaluate_on": ["M15"],
      "transitions": [
        {
          "to": "in_position_short",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "ind.h4_smc_structure.ote_bottom", "description": "Price at or above OTE bottom (for bearish: 61.8% retracement up)"},
              {"left": "_price", "operator": "<=", "right": "ind.h4_smc_structure.ote_top", "description": "Price at or below OTE top (for bearish: 78.6% retracement up)"},
              {"left": "ind.m15_rsi.value", "operator": ">", "right": "65", "description": "M15 RSI overbought — momentum exhaustion on rally"},
              {"left": "_price", "operator": "<", "right": "var.strong_high", "description": "Price still below protected high — structure intact"}
            ]
          },
          "actions": [
            {"set_var": "entry_price", "expr": "_price"},
            {"set_var": "initial_sl", "expr": "var.strong_high + ind.h4_atr.value * 0.5"},
            {"set_var": "initial_tp", "expr": "_price - (var.initial_sl - _price) * 3"},
            {"open_trade": {
              "direction": "SELL",
              "lot": {"expr": "risk.max_lot"},
              "sl": {"expr": "var.strong_high + ind.h4_atr.value * 0.5"},
              "tp": {"expr": "_price - (var.initial_sl - _price) * 3"}
            }},
            {"log": "SHORT entry in OTE zone — SL above strong high, TP at 3R"}
          ]
        },
        {
          "to": "idle",
          "priority": 0,
          "conditions": {
            "type": "OR",
            "rules": [
              {"left": "_price", "operator": ">", "right": "var.strong_high", "description": "Price broke above strong high — bearish structure invalidated"},
              {"left": "ind.h4_smc_structure.trend", "operator": "!=", "right": "-1", "description": "H4 structure no longer bearish"}
            ]
          },
          "actions": [
            {"log": "Short setup invalidated — returning to idle"}
          ]
        }
      ],
      "timeout": {"bars": 30, "timeframe": "M15", "to": "idle"}
    },
    "in_position_long": {
      "description": "Manage long position: breakeven at 1R, partial close at 2R, trail with ATR after 2R. Exit on structure reversal.",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "-1", "description": "H4 structure reversed to bearish — exit immediately"}
            ]
          },
          "actions": [
            {"close_trade": true},
            {"log": "Closing LONG — H4 structure reversal to bearish"}
          ]
        }
      ],
      "position_management": [
        {
          "name": "breakeven_at_1rr",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl)", "description": "Price reached 1R profit (risk distance above entry)"}
            ]
          },
          "modify_sl": {"expr": "trade.open_price + ind.h4_atr.value * 0.1"}
        },
        {
          "name": "partial_close_at_2rr",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl) * 2", "description": "Price reached 2R profit"}
            ]
          },
          "partial_close": {"pct": 50}
        },
        {
          "name": "trail_sl_after_2rr",
          "continuous": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "trade.open_price + (trade.open_price - var.initial_sl) * 2", "description": "Price past 2R — trail active"}
            ]
          },
          "trail_sl": {
            "distance": {"expr": "ind.h4_atr.value * 1.0"},
            "step": {"expr": "ind.h4_atr.value * 0.2"}
          }
        }
      ],
      "on_trade_closed": {"to": "idle"}
    },
    "in_position_short": {
      "description": "Manage short position: breakeven at 1R, partial close at 2R, trail with ATR after 2R. Exit on structure reversal.",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc_structure.trend", "operator": "==", "right": "1", "description": "H4 structure reversed to bullish — exit immediately"}
            ]
          },
          "actions": [
            {"close_trade": true},
            {"log": "Closing SHORT — H4 structure reversal to bullish"}
          ]
        }
      ],
      "position_management": [
        {
          "name": "breakeven_at_1rr",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<=", "right": "trade.open_price - (var.initial_sl - trade.open_price)", "description": "Price reached 1R profit (short direction)"}
            ]
          },
          "modify_sl": {"expr": "trade.open_price - ind.h4_atr.value * 0.1"}
        },
        {
          "name": "partial_close_at_2rr",
          "once": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<=", "right": "trade.open_price - (var.initial_sl - trade.open_price) * 2", "description": "Price reached 2R profit (short direction)"}
            ]
          },
          "partial_close": {"pct": 50}
        },
        {
          "name": "trail_sl_after_2rr",
          "continuous": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<=", "right": "trade.open_price - (var.initial_sl - trade.open_price) * 2", "description": "Price past 2R (short direction)"}
            ]
          },
          "trail_sl": {
            "distance": {"expr": "ind.h4_atr.value * 1.0"},
            "step": {"expr": "ind.h4_atr.value * 0.2"}
          }
        }
      ],
      "on_trade_closed": {"to": "idle"}
    }
  },
  "initial_phase": "idle",
  "risk": {
    "max_lot": 0.1,
    "max_daily_trades": 3,
    "max_drawdown_pct": 3.0,
    "max_open_positions": 1
  }
}
```

### Phase Flow Walkthrough

1. **`idle`** (evaluates on H4 bar close)
   - Checks H4 SMC_Structure trend. If bullish and RSI < 60 and ATR > 2.0, stores structure levels in variables and transitions to `wait_entry_long`. If bearish with the inverse conditions, transitions to `wait_entry_short`.

2. **`wait_entry_long`** (evaluates on M15 bar close)
   - Waits for price to pull back into the H4 OTE zone (61.8%--78.6% Fibonacci retracement of the structural swing). Requires M15 RSI < 35 for momentum exhaustion confirmation and price still above the strong low (structure intact).
   - On entry: stores entry price and computes SL (below strong low with ATR buffer) and TP (3:1 R:R). Opens BUY trade.
   - Invalidation: if price breaks below strong low or H4 structure turns non-bullish, returns to idle.
   - Timeout: 30 M15 bars (7.5 hours) with no entry triggers a return to idle.

3. **`in_position_long`** (evaluates on M15 and H4 bar close)
   - Structure reversal exit: if H4 trend flips to bearish, immediately closes the trade.
   - Breakeven at 1R: when unrealized profit equals the initial risk distance, moves SL to entry + 0.1 ATR.
   - Partial close at 2R: when unrealized profit equals 2x risk distance, closes 50% of the position.
   - Trailing stop after 2R: continuously trails SL by 1.0 ATR distance with 0.2 ATR minimum step.
   - On trade closed (SL hit, TP hit, or manual): transitions back to idle.

4. **`wait_entry_short`** / **`in_position_short`** -- mirror logic for the bearish direction with inverted conditions and SELL orders.

---

## API Reference

### Playbook Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/playbooks` | Build a new playbook from natural language |
| `GET` | `/api/playbooks` | List all playbooks |
| `GET` | `/api/playbooks/:id` | Get playbook with full config |
| `PUT` | `/api/playbooks/:id` | Update playbook config or metadata |
| `DELETE` | `/api/playbooks/:id` | Delete a playbook |
| `PUT` | `/api/playbooks/:id/toggle` | Enable or disable a playbook |
| `POST` | `/api/playbooks/:id/refine` | AI-assisted refinement with journal data |
| `GET` | `/api/playbooks/:id/state` | Get current runtime state |

### Build Request

```json
POST /api/playbooks
{
  "description": "Buy XAUUSD when H4 shows bullish smart money structure and M15 RSI pulls back below 35 into the OTE zone. Use ATR for SL/TP sizing with 3:1 reward-to-risk."
}
```

### Build Response

```json
{
  "id": 1,
  "name": "SMC OTE Gold Swing",
  "config": { ... },
  "skills_used": ["SMC_Structure", "RSI", "ATR"],
  "usage": {
    "model": "claude-opus-4-20250514",
    "prompt_tokens": 8432,
    "completion_tokens": 2156,
    "duration_ms": 12340
  }
}
```

### Refine Request

```json
POST /api/playbooks/1/refine
{
  "messages": [
    {"role": "user", "content": "The win rate is only 35%. Most losses are SL hits within the first few bars. What should I change?"}
  ]
}
```

### Refine Response

```json
{
  "reply": "### Analysis\n- 65% of losses are SL hits occurring within 3 bars of entry...\n\n### Recommendations\n1. Widen SL buffer from 0.5 ATR to 0.8 ATR...\n\n<playbook_update>{...}</playbook_update>",
  "updated": true,
  "config": { ... }
}
```
