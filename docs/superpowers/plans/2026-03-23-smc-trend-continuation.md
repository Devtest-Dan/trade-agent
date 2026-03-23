# SMC Trend Continuation Strategy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a working playbook JSON for the SMC Trend Continuation strategy (EURUSD, H4 bias + M15 entry) and validate it via backtest.

**Architecture:** Single playbook JSON file conforming to `playbook-v1` schema. Split long/short phase machine with 7 phases. Uses `modify_sl` for NWE band trailing. Loaded into the system via the playbooks API or direct DB insert.

**Tech Stack:** Python (FastAPI backend), PlaybookConfig Pydantic models, backtest engine, expression evaluator

**Spec:** `docs/superpowers/specs/2026-03-23-smc-trend-continuation-design.md`

---

### Task 1: Create the Playbook JSON File

**Files:**
- Create: `data/playbooks/smc_trend_continuation_eurusd.json`

- [ ] **Step 1: Write the complete playbook JSON**

```json
{
  "$schema": "playbook-v1",
  "id": "smc-trend-continuation-eurusd",
  "name": "SMC Trend Continuation (EURUSD)",
  "description": "H4 SMC directional bias + M15 NWE pullback + M15 RSI Kernel momentum trigger. Split long/short phases. NWE band trailing via modify_sl.",
  "symbols": ["EURUSD"],
  "autonomy": "full_auto",
  "indicators": [
    {
      "id": "h4_smc",
      "name": "SMC_Structure",
      "timeframe": "H4",
      "params": {"swing_len": 10}
    },
    {
      "id": "m15_nwe",
      "name": "NW_Envelope",
      "timeframe": "M15",
      "params": {
        "lookback_window": 8,
        "relative_weighting": 8.0,
        "start_bar": 25,
        "atr_length": 60,
        "near_factor": 1.5,
        "far_factor": 8.0
      }
    },
    {
      "id": "m15_rsi_kernel",
      "name": "RSI_Kernel",
      "timeframe": "M15",
      "params": {
        "rsi_length": 14,
        "kernel_lookback": 8,
        "kernel_weight": 8.0,
        "kernel_start": 25,
        "kernel_smooth": true,
        "kernel_smooth_period": 4,
        "ob_level": 70,
        "os_level": 30
      }
    },
    {
      "id": "h4_atr",
      "name": "ATR",
      "timeframe": "H4",
      "params": {"length": 14}
    }
  ],
  "variables": {
    "initial_sl": {"type": "float", "default": 0.0},
    "initial_tp": {"type": "float", "default": 0.0}
  },
  "initial_phase": "idle",
  "phases": {
    "idle": {
      "description": "Wait for H4 SMC directional bias",
      "evaluate_on": ["H4"],
      "transitions": [
        {
          "to": "scanning_long",
          "priority": 2,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc.trend", "operator": "==", "right": "1.0", "description": "H4 SMC bullish trend"},
              {"left": "ind.h4_smc.zone", "operator": "==", "right": "-1.0", "description": "Price in discount zone"}
            ]
          },
          "actions": []
        },
        {
          "to": "scanning_short",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc.trend", "operator": "==", "right": "-1.0", "description": "H4 SMC bearish trend"},
              {"left": "ind.h4_smc.zone", "operator": "==", "right": "1.0", "description": "Price in premium zone"}
            ]
          },
          "actions": []
        }
      ],
      "timeout": null,
      "position_management": [],
      "on_trade_closed": null
    },

    "scanning_long": {
      "description": "Bullish bias confirmed — watch M15 NWE for pullback to lower band",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "entry_ready_long",
          "priority": 2,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<=", "right": "ind.m15_nwe.lower_near", "description": "Price at or below M15 NWE lower near band"}
            ]
          },
          "actions": []
        },
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "OR",
            "rules": [
              {"left": "ind.h4_smc.trend", "operator": "!=", "right": "1.0", "description": "H4 trend no longer bullish"},
              {"left": "ind.h4_smc.zone", "operator": "!=", "right": "-1.0", "description": "No longer in discount zone"}
            ]
          },
          "actions": []
        }
      ],
      "timeout": {"bars": 200, "timeframe": "M15", "to": "idle"},
      "position_management": [],
      "on_trade_closed": null
    },

    "scanning_short": {
      "description": "Bearish bias confirmed — watch M15 NWE for pullback to upper band",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "entry_ready_short",
          "priority": 2,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">=", "right": "ind.m15_nwe.upper_near", "description": "Price at or above M15 NWE upper near band"}
            ]
          },
          "actions": []
        },
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "OR",
            "rules": [
              {"left": "ind.h4_smc.trend", "operator": "!=", "right": "-1.0", "description": "H4 trend no longer bearish"},
              {"left": "ind.h4_smc.zone", "operator": "!=", "right": "1.0", "description": "No longer in premium zone"}
            ]
          },
          "actions": []
        }
      ],
      "timeout": {"bars": 200, "timeframe": "M15", "to": "idle"},
      "position_management": [],
      "on_trade_closed": null
    },

    "entry_ready_long": {
      "description": "Pullback detected — wait for M15 RSI Kernel cross above for long entry",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "in_trade_long",
          "priority": 3,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.m15_rsi_kernel.rsi_cross_above", "operator": "==", "right": "1.0", "description": "RSI crosses above kernel — momentum trigger"}
            ]
          },
          "actions": [
            {"set_var": "initial_sl", "expr": "iff(ind.h4_smc.ob_type == 1.0, iff(ind.h4_smc.ob_lower < _price, ind.h4_smc.ob_lower, _price - ind.h4_atr.value * 2.0), _price - ind.h4_atr.value * 2.0)"},
            {"set_var": "initial_tp", "expr": "iff(ind.h4_smc.fvg_type == -1.0, ind.h4_smc.fvg_upper, iff(ind.h4_smc.ob_type == -1.0, ind.h4_smc.ob_lower, _price + ind.h4_atr.value * 3.0))"},
            {
              "open_trade": {
                "direction": "BUY",
                "sl": {"expr": "var.initial_sl"},
                "tp": {"expr": "var.initial_tp"}
              }
            }
          ]
        },
        {
          "to": "scanning_long",
          "priority": 2,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": ">", "right": "ind.m15_nwe.yhat", "description": "Price returned above NWE midline without triggering"}
            ]
          },
          "actions": []
        },
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc.trend", "operator": "!=", "right": "1.0", "description": "H4 bullish bias lost"}
            ]
          },
          "actions": []
        }
      ],
      "timeout": {"bars": 50, "timeframe": "M15", "to": "scanning_long"},
      "position_management": [],
      "on_trade_closed": null
    },

    "entry_ready_short": {
      "description": "Pullback detected — wait for M15 RSI Kernel cross below for short entry",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "in_trade_short",
          "priority": 3,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.m15_rsi_kernel.rsi_cross_below", "operator": "==", "right": "1.0", "description": "RSI crosses below kernel — momentum trigger"}
            ]
          },
          "actions": [
            {"set_var": "initial_sl", "expr": "iff(ind.h4_smc.ob_type == -1.0, iff(ind.h4_smc.ob_upper > _price, ind.h4_smc.ob_upper, _price + ind.h4_atr.value * 2.0), _price + ind.h4_atr.value * 2.0)"},
            {"set_var": "initial_tp", "expr": "iff(ind.h4_smc.fvg_type == 1.0, ind.h4_smc.fvg_lower, iff(ind.h4_smc.ob_type == 1.0, ind.h4_smc.ob_upper, _price - ind.h4_atr.value * 3.0))"},
            {
              "open_trade": {
                "direction": "SELL",
                "sl": {"expr": "var.initial_sl"},
                "tp": {"expr": "var.initial_tp"}
              }
            }
          ]
        },
        {
          "to": "scanning_short",
          "priority": 2,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "_price", "operator": "<", "right": "ind.m15_nwe.yhat", "description": "Price returned below NWE midline without triggering"}
            ]
          },
          "actions": []
        },
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc.trend", "operator": "!=", "right": "-1.0", "description": "H4 bearish bias lost"}
            ]
          },
          "actions": []
        }
      ],
      "timeout": {"bars": 50, "timeframe": "M15", "to": "scanning_short"},
      "position_management": [],
      "on_trade_closed": null
    },

    "in_trade_long": {
      "description": "Long position open — manage with breakeven + NWE trailing + CHoCH exit",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc.choch_bear", "operator": "==", "right": "1.0", "description": "Bearish CHoCH — trend reversal, close immediately"}
            ]
          },
          "actions": [
            {"close_trade": true}
          ]
        }
      ],
      "timeout": {"bars": 500, "timeframe": "M15", "to": "idle"},
      "position_management": [
        {
          "name": "breakeven_long",
          "once": true,
          "continuous": false,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "trade.pnl", "operator": ">", "right": "ind.h4_atr.value * 1.0", "description": "Profit exceeds 1x ATR"}
            ]
          },
          "modify_sl": {"expr": "trade.open_price"}
        },
        {
          "name": "nwe_trail_long",
          "once": false,
          "continuous": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "trade.pnl", "operator": ">", "right": "ind.h4_atr.value * 1.5", "description": "Profit exceeds 1.5x ATR"},
              {"left": "ind.m15_nwe.lower_near", "operator": ">", "right": "trade.sl", "description": "NWE lower_near is above current SL — tighten only"}
            ]
          },
          "modify_sl": {"expr": "ind.m15_nwe.lower_near"}
        }
      ],
      "on_trade_closed": {"to": "idle"}
    },

    "in_trade_short": {
      "description": "Short position open — manage with breakeven + NWE trailing + CHoCH exit",
      "evaluate_on": ["M15", "H4"],
      "transitions": [
        {
          "to": "idle",
          "priority": 1,
          "conditions": {
            "type": "AND",
            "rules": [
              {"left": "ind.h4_smc.choch_bull", "operator": "==", "right": "1.0", "description": "Bullish CHoCH — trend reversal, close immediately"}
            ]
          },
          "actions": [
            {"close_trade": true}
          ]
        }
      ],
      "timeout": {"bars": 500, "timeframe": "M15", "to": "idle"},
      "position_management": [
        {
          "name": "breakeven_short",
          "once": true,
          "continuous": false,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "trade.pnl", "operator": ">", "right": "ind.h4_atr.value * 1.0", "description": "Profit exceeds 1x ATR"}
            ]
          },
          "modify_sl": {"expr": "trade.open_price"}
        },
        {
          "name": "nwe_trail_short",
          "once": false,
          "continuous": true,
          "when": {
            "type": "AND",
            "rules": [
              {"left": "trade.pnl", "operator": ">", "right": "ind.h4_atr.value * 1.5", "description": "Profit exceeds 1.5x ATR"},
              {"left": "ind.m15_nwe.upper_near", "operator": "<", "right": "trade.sl", "description": "NWE upper_near is below current SL — tighten only"}
            ]
          },
          "modify_sl": {"expr": "ind.m15_nwe.upper_near"}
        }
      ],
      "on_trade_closed": {"to": "idle"}
    }
  },
  "risk": {
    "max_lot": 0.1,
    "max_daily_trades": 3,
    "max_drawdown_pct": 5.0,
    "max_open_positions": 1
  }
}
```

- [ ] **Step 2: Validate the JSON parses correctly**

Run:
```bash
cd D:\trade-agent && python -c "
import json
from agent.models.playbook import PlaybookConfig
with open('data/playbooks/smc_trend_continuation_eurusd.json') as f:
    data = json.load(f)
config = PlaybookConfig(**data)
print(f'OK: {config.name}')
print(f'Phases: {list(config.phases.keys())}')
print(f'Indicators: {[i.id for i in config.indicators]}')
print(f'Variables: {list(config.variables.keys())}')
"
```

Expected: `OK: SMC Trend Continuation (EURUSD)` with 7 phases listed, 4 indicators, 2 variables.

- [ ] **Step 3: Commit the playbook JSON**

```bash
cd D:\trade-agent
git add data/playbooks/smc_trend_continuation_eurusd.json
git commit -m "feat: add SMC Trend Continuation playbook for EURUSD"
```

---

### Task 2: Load Playbook into the Database

**Files:**
- No new files — uses existing API

- [ ] **Step 1: Load playbook via Python script**

Run:
```bash
cd D:\trade-agent && python -c "
import json, asyncio
from agent.models.playbook import Playbook, PlaybookConfig
from agent.db.database import Database

async def load():
    db = Database()
    await db.connect()
    with open('data/playbooks/smc_trend_continuation_eurusd.json') as f:
        data = json.load(f)
    config = PlaybookConfig(**data)
    playbook = Playbook(
        name=config.name,
        description_nl='H4 SMC directional bias + M15 NWE pullback + M15 RSI Kernel momentum trigger. EURUSD trend continuation.',
        explanation='Phase machine: idle -> scanning_long/short -> entry_ready_long/short -> in_trade_long/short. Breakeven at 1R, NWE band trailing at 1.5R. CHoCH exit.',
        config=config,
        enabled=False,
    )
    pid = await db.create_playbook(playbook)
    print(f'Playbook created with ID: {pid}')
    await db.disconnect()

asyncio.run(load())
"
```

Expected: `Playbook created with ID: <number>`

- [ ] **Step 2: Verify playbook appears in dashboard**

Open `http://localhost:5173` → navigate to Playbooks section → confirm "SMC Trend Continuation (EURUSD)" appears.

---

### Task 3: Run Backtest

**Files:**
- No new files — uses existing backtest engine

- [ ] **Step 1: Identify the playbook ID and run backtest via API**

Run:
```bash
cd D:\trade-agent && curl -s http://localhost:8000/api/playbooks | python -m json.tool | head -20
```

Find the playbook ID for "SMC Trend Continuation (EURUSD)".

- [ ] **Step 2: Trigger backtest via dashboard**

Open `http://localhost:5173` → Playbooks → select "SMC Trend Continuation (EURUSD)" → click Backtest.

Configure:
- Symbol: EURUSD
- Timeframe: M15 (primary evaluation timeframe)
- Date range: at least 3 months of data (or whatever is available)
- Click Run

- [ ] **Step 3: Analyze results**

Review in dashboard:
- Total trades, win rate, profit factor
- Drawdown curve
- Per-trade journal (check entry/exit logic fired correctly)
- Phase transition log (verify the state machine flows as expected)

- [ ] **Step 4: Commit any adjustments**

If parameter tuning is needed based on backtest results:
```bash
cd D:\trade-agent
git add data/playbooks/smc_trend_continuation_eurusd.json
git commit -m "tune: adjust SMC Trend Continuation parameters after backtest"
```

---

### Task 4: Push to GitHub

- [ ] **Step 1: Push all commits**

```bash
cd D:\trade-agent && git push origin master
```
