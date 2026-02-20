# Trade Agent API Reference

**Base URL:** `http://localhost:8000`
**Protocol:** HTTP/1.1, WebSocket
**Content-Type:** `application/json`
**Authentication:** JWT Bearer Token (unless noted otherwise)

---

## Table of Contents

- [Authentication](#authentication)
- [Health Check](#health-check)
- [Strategies (Legacy)](#strategies-legacy)
- [Playbooks](#playbooks)
- [Trade Journal](#trade-journal)
- [Signals](#signals)
- [Trades](#trades)
- [Market Data](#market-data)
- [Settings](#settings)
- [Kill Switch](#kill-switch)
- [WebSocket](#websocket)
- [Error Responses](#error-responses)

---

## Authentication

All endpoints except `/api/health` and `/api/auth/*` require a JWT Bearer token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Tokens are obtained via the register or login endpoints below.

---

### POST /api/auth/register

Create a new user account and receive a JWT token.

**Authentication:** None required

**Request:**

```json
{
  "username": "string",
  "password": "string"
}
```

**Response (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "trader1", "password": "securePass123"}'
```

---

### POST /api/auth/login

Authenticate an existing user and receive a JWT token.

**Authentication:** None required

**Request:**

```json
{
  "username": "string",
  "password": "string"
}
```

**Response (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "trader1", "password": "securePass123"}'
```

---

## Health Check

### GET /api/health

Returns the current health status of the Trade Agent backend, including MT5 connectivity and kill switch state.

**Authentication:** None required

**Response (200 OK):**

```json
{
  "status": "ok",
  "mt5_connected": true,
  "kill_switch": false
}
```

| Field            | Type    | Description                                      |
|------------------|---------|--------------------------------------------------|
| `status`         | string  | `"ok"` when the server is running                |
| `mt5_connected`  | boolean | Whether the ZeroMQ bridge to MT5 EA is connected |
| `kill_switch`    | boolean | Whether the emergency kill switch is active       |

**Example:**

```bash
curl http://localhost:8000/api/health
```

---

## Strategies (Legacy)

Strategy endpoints use Claude AI to parse natural language trading descriptions into structured strategy configurations. These are the original strategy system; see [Playbooks](#playbooks) for the newer, phase-based system.

---

### POST /api/strategies

Create a new strategy from a natural language description. The description is sent to Claude AI, which parses it into a structured strategy configuration with filters, triggers, risk parameters, and management rules.

**Request:**

```json
{
  "description": "Buy XAUUSD when RSI < 30 on H4 and price is above the 200 EMA on D1. Risk 1% per trade with a 2:1 reward ratio. Use a trailing stop after 1R profit."
}
```

**Response (201 Created):**

```json
{
  "id": 1,
  "name": "XAUUSD RSI Oversold + EMA Trend",
  "description_nl": "Buy XAUUSD when RSI < 30 on H4 and price is above the 200 EMA on D1...",
  "config": {
    "symbol": "XAUUSD",
    "direction": "LONG",
    "timeframe": "H4",
    "filters": [
      {
        "indicator": "EMA",
        "timeframe": "D1",
        "params": { "period": 200 },
        "condition": "price_above"
      }
    ],
    "triggers": [
      {
        "indicator": "RSI",
        "timeframe": "H4",
        "params": { "period": 14 },
        "condition": "below",
        "value": 30
      }
    ],
    "risk": {
      "risk_pct": 1.0,
      "rr_ratio": 2.0
    },
    "management": {
      "trailing_stop_after_rr": 1.0
    }
  },
  "autonomy": "signal_only",
  "enabled": false,
  "created_at": "2026-02-20T10:30:00Z"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/strategies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "Buy XAUUSD when RSI < 30 on H4 and price is above 200 EMA on D1"}'
```

---

### GET /api/strategies

List all strategies for the authenticated user.

**Response (200 OK):**

```json
[
  {
    "id": 1,
    "name": "XAUUSD RSI Oversold + EMA Trend",
    "description_nl": "Buy XAUUSD when RSI < 30 on H4...",
    "autonomy": "signal_only",
    "enabled": true,
    "created_at": "2026-02-20T10:30:00Z"
  },
  {
    "id": 2,
    "name": "EURUSD Breakout Strategy",
    "description_nl": "Trade breakouts on EURUSD M15...",
    "autonomy": "semi_auto",
    "enabled": false,
    "created_at": "2026-02-20T11:00:00Z"
  }
]
```

**Example:**

```bash
curl http://localhost:8000/api/strategies \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/strategies/:id

Retrieve a single strategy with its full configuration.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The strategy ID          |

**Response (200 OK):**

```json
{
  "id": 1,
  "name": "XAUUSD RSI Oversold + EMA Trend",
  "description_nl": "Buy XAUUSD when RSI < 30 on H4...",
  "config": {
    "symbol": "XAUUSD",
    "direction": "LONG",
    "timeframe": "H4",
    "filters": [ ... ],
    "triggers": [ ... ],
    "risk": { ... },
    "management": { ... }
  },
  "autonomy": "signal_only",
  "enabled": true,
  "created_at": "2026-02-20T10:30:00Z"
}
```

**Example:**

```bash
curl http://localhost:8000/api/strategies/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

### PUT /api/strategies/:id

Update a strategy with partial fields. Only the fields provided will be updated.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The strategy ID          |

**Request:**

```json
{
  "name": "Updated Strategy Name",
  "config": {
    "risk": {
      "risk_pct": 0.5,
      "rr_ratio": 3.0
    }
  }
}
```

**Response (200 OK):**

```json
{
  "id": 1,
  "name": "Updated Strategy Name",
  "description_nl": "Buy XAUUSD when RSI < 30 on H4...",
  "config": { ... },
  "autonomy": "signal_only",
  "enabled": true,
  "created_at": "2026-02-20T10:30:00Z"
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/strategies/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Strategy Name"}'
```

---

### DELETE /api/strategies/:id

Delete a strategy permanently.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The strategy ID          |

**Response (200 OK):**

```json
{
  "status": "deleted"
}
```

**Example:**

```bash
curl -X DELETE http://localhost:8000/api/strategies/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

### PUT /api/strategies/:id/autonomy

Set the autonomy level for a strategy.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The strategy ID          |

**Request:**

```json
{
  "autonomy": "signal_only"
}
```

**Autonomy Levels:**

| Level         | Description                                                    |
|---------------|----------------------------------------------------------------|
| `signal_only` | Generates signals only; user must manually approve/reject      |
| `semi_auto`   | Generates signals and opens trades with user confirmation      |
| `full_auto`   | Fully autonomous; generates signals and executes automatically |

**Response (200 OK):**

```json
{
  "id": 1,
  "autonomy": "signal_only"
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/strategies/1/autonomy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"autonomy": "semi_auto"}'
```

---

### PUT /api/strategies/:id/toggle

Toggle a strategy between enabled and disabled states.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The strategy ID          |

**Response (200 OK):**

```json
{
  "enabled": true
}
```

Calling again:

```json
{
  "enabled": false
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/strategies/1/toggle \
  -H "Authorization: Bearer $TOKEN"
```

---

### POST /api/strategies/:id/chat

Multi-turn AI chat for refining and discussing a strategy. Sends the conversation history along with the current strategy configuration to Claude for contextual assistance.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The strategy ID          |

**Request:**

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Can you add a volume filter to confirm the RSI signal?"
    }
  ]
}
```

**Response (200 OK):**

```json
{
  "reply": "I can add a volume confirmation filter. I'll add a condition that requires the current volume to be at least 1.5x the 20-period average volume on the H4 timeframe. This helps filter out weak RSI signals that occur during low-liquidity periods. Would you like me to apply this change?"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/strategies/1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Can you add a volume filter?"}]}'
```

---

## Playbooks

Playbooks are the newer, phase-based strategy system. Each playbook defines a state machine with phases, transitions, entry conditions, exit rules, and position management. Playbooks are built from natural language using Claude Opus with indicator skills files for accurate parsing.

---

### POST /api/playbooks

Build a new playbook from a natural language description. The description is sent to Claude Opus along with the full indicator skills catalog, producing a structured `PlaybookConfig` with phases, conditions, and management rules.

**Request:**

```json
{
  "description": "SMC OTE strategy: identify structure break on H4, wait for pullback to 61.8-78.6 fib zone on H1, enter when RSI crosses above 30. Use 1.5R take profit with breakeven at 1R."
}
```

**Response (201 Created):**

```json
{
  "id": 1,
  "name": "SMC OTE Re-Entry Strategy",
  "config": {
    "symbols": ["XAUUSD"],
    "phases": {
      "idle": {
        "conditions": [
          {
            "indicator": "SMC_Structure",
            "timeframe": "H4",
            "check": "bullish_break"
          }
        ],
        "transitions": {
          "wait_pullback_long": "all_conditions_met"
        }
      },
      "wait_pullback_long": {
        "conditions": [
          {
            "indicator": "Fibonacci",
            "timeframe": "H1",
            "check": "price_in_zone",
            "params": { "low": 0.618, "high": 0.786 }
          }
        ],
        "transitions": {
          "entry_ready_long": "all_conditions_met",
          "idle": "timeout_bars > 20"
        }
      },
      "entry_ready_long": {
        "conditions": [
          {
            "indicator": "RSI",
            "timeframe": "H1",
            "check": "crosses_above",
            "value": 30
          }
        ],
        "action": "open_long",
        "transitions": {
          "in_position_long": "trade_opened",
          "idle": "timeout_bars > 5"
        }
      },
      "in_position_long": {
        "management": {
          "tp_rr": 1.5,
          "breakeven_at_rr": 1.0
        },
        "transitions": {
          "idle": "trade_closed"
        }
      }
    },
    "risk": {
      "risk_pct": 1.0,
      "max_concurrent": 1
    }
  },
  "skills_used": ["RSI", "SMC_Structure", "ATR"],
  "usage": {
    "model": "claude-opus-4-20250514",
    "prompt_tokens": 12500,
    "completion_tokens": 3200,
    "duration_ms": 8500
  }
}
```

| Response Field | Type     | Description                                              |
|----------------|----------|----------------------------------------------------------|
| `id`           | int      | Unique playbook ID                                       |
| `name`         | string   | AI-generated name based on the strategy description      |
| `config`       | object   | Full `PlaybookConfig` with phases, conditions, and rules |
| `skills_used`  | string[] | Indicator skills referenced during parsing               |
| `usage`        | object   | Claude API usage stats (model, tokens, duration)         |

**Example:**

```bash
curl -X POST http://localhost:8000/api/playbooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "SMC OTE strategy with RSI trigger on H1 pullback to fib zone"}'
```

---

### GET /api/playbooks

List all playbooks for the authenticated user. Returns summary objects without the full config.

**Response (200 OK):**

```json
[
  {
    "id": 1,
    "name": "SMC OTE Re-Entry Strategy",
    "description_nl": "SMC OTE strategy: identify structure break on H4...",
    "enabled": false,
    "autonomy": "semi_auto",
    "symbols": ["XAUUSD"],
    "phases": ["idle", "wait_pullback_long", "entry_ready_long", "in_position_long"],
    "created_at": "2026-02-20T10:30:00Z"
  },
  {
    "id": 2,
    "name": "London Session Breakout",
    "description_nl": "Trade London session breakouts on GBPUSD...",
    "enabled": true,
    "autonomy": "full_auto",
    "symbols": ["GBPUSD"],
    "phases": ["idle", "range_forming", "breakout_detected", "in_position"],
    "created_at": "2026-02-20T14:00:00Z"
  }
]
```

**Example:**

```bash
curl http://localhost:8000/api/playbooks \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/playbooks/:id

Retrieve a single playbook with its complete configuration JSON.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The playbook ID          |

**Response (200 OK):**

Returns the full playbook object including the complete `config` field with all phases, conditions, transitions, and management rules. Structure matches the response from `POST /api/playbooks`.

**Example:**

```bash
curl http://localhost:8000/api/playbooks/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

### PUT /api/playbooks/:id

Update a playbook's name, configuration, or autonomy level.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The playbook ID          |

**Request:**

```json
{
  "name": "SMC OTE v2",
  "config": {
    "risk": {
      "risk_pct": 0.5,
      "max_concurrent": 2
    }
  },
  "autonomy": "full_auto"
}
```

All fields are optional; only provided fields are updated.

**Response (200 OK):**

```json
{
  "status": "updated"
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/playbooks/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"autonomy": "full_auto"}'
```

---

### DELETE /api/playbooks/:id

Delete a playbook permanently. If the playbook is currently running, it will be stopped first.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The playbook ID          |

**Response (200 OK):**

```json
{
  "status": "deleted"
}
```

**Example:**

```bash
curl -X DELETE http://localhost:8000/api/playbooks/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

### PUT /api/playbooks/:id/toggle

Toggle a playbook between enabled and disabled states. When enabled, the playbook is loaded into the `PlaybookEngine` and begins evaluating market conditions. When disabled, it is unloaded and stops processing.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The playbook ID          |

**Response (200 OK):**

```json
{
  "enabled": true
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/playbooks/1/toggle \
  -H "Authorization: Bearer $TOKEN"
```

---

### POST /api/playbooks/:id/refine

AI-assisted playbook refinement using trade journal data. Sends the current playbook configuration, journal analytics, per-condition win rates, and recent trade samples to Claude Sonnet for intelligent analysis and optimization suggestions.

The AI may return an updated configuration if the refinement warrants concrete changes.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The playbook ID          |

**Request:**

```json
{
  "messages": [
    {
      "role": "user",
      "content": "The win rate is low, can you tighten the entry conditions?"
    }
  ]
}
```

**Response (200 OK):**

```json
{
  "reply": "Looking at your journal data, I can see the RSI condition has a 40% win rate which is dragging down overall performance. I recommend changing the RSI threshold from 30 to 25 and adding a volume confirmation filter. I've also tightened the Fibonacci zone from 61.8-78.6 to 65-78.6 to filter out shallow pullbacks. These changes have been applied to your config.",
  "updated": true,
  "config": {
    "phases": {
      "entry_ready_long": {
        "conditions": [
          {
            "indicator": "RSI",
            "timeframe": "H1",
            "check": "crosses_above",
            "value": 25
          },
          {
            "indicator": "Volume",
            "timeframe": "H1",
            "check": "above_average",
            "params": { "period": 20, "multiplier": 1.2 }
          }
        ]
      }
    }
  }
}
```

| Response Field | Type    | Description                                              |
|----------------|---------|----------------------------------------------------------|
| `reply`        | string  | AI analysis and explanation text                         |
| `updated`      | boolean | Whether the AI produced config changes                   |
| `config`       | object  | Updated PlaybookConfig (present only when `updated=true`)|

**Example:**

```bash
curl -X POST http://localhost:8000/api/playbooks/1/refine \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "The win rate is low, can you tighten the entry conditions?"}]}'
```

---

### GET /api/playbooks/:id/state

Get the runtime state of a running playbook instance. Shows the current phase, internal variables, bars elapsed, and open trade information.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The playbook ID          |

**Response (200 OK):**

```json
{
  "playbook_id": 1,
  "symbol": "XAUUSD",
  "current_phase": "wait_pullback_long",
  "variables": {
    "structure_break_price": 2780.0,
    "structure_break_bar": 142
  },
  "bars_in_phase": 5,
  "phase_timeframe_bars": {
    "H4": 5,
    "H1": 20
  },
  "fired_once_rules": [],
  "open_ticket": null,
  "open_direction": null
}
```

| Response Field          | Type        | Description                                          |
|-------------------------|-------------|------------------------------------------------------|
| `playbook_id`           | int         | The playbook ID                                      |
| `symbol`                | string      | Symbol being tracked                                 |
| `current_phase`         | string      | Active phase name from the playbook's state machine  |
| `variables`             | object      | Internal state variables set during phase transitions|
| `bars_in_phase`         | int         | Number of bars elapsed in the current phase          |
| `phase_timeframe_bars`  | object      | Bar count per timeframe in the current phase         |
| `fired_once_rules`      | string[]    | Management rules that have already triggered         |
| `open_ticket`           | int \| null | MT5 ticket number if a trade is open                 |
| `open_direction`        | string \| null | `"BUY"` or `"SELL"` if a trade is open            |

**Example:**

```bash
curl http://localhost:8000/api/playbooks/1/state \
  -H "Authorization: Bearer $TOKEN"
```

---

## Trade Journal

The trade journal automatically records every trade executed by the agent, including full indicator snapshots at entry and exit, management events, and market context.

---

### GET /api/journal

Query journal entries with optional filters.

**Query Parameters:**

| Parameter     | Type   | Required | Description                                  |
|---------------|--------|----------|----------------------------------------------|
| `playbook_id` | int    | No       | Filter by playbook ID                        |
| `strategy_id` | int    | No       | Filter by legacy strategy ID                 |
| `symbol`      | string | No       | Filter by symbol (e.g., `XAUUSD`)            |
| `outcome`     | string | No       | Filter by outcome: `win`, `loss`, `breakeven`|
| `limit`       | int    | No       | Max entries to return (default: 50)          |
| `offset`      | int    | No       | Pagination offset (default: 0)               |

**Response (200 OK):**

```json
[
  {
    "id": 1,
    "symbol": "XAUUSD",
    "direction": "BUY",
    "pnl": 90.0,
    "pnl_pips": 900.0,
    "rr_achieved": 1.89,
    "outcome": "win",
    "exit_reason": "tp_hit",
    "created_at": "2026-02-20T12:00:00Z"
  },
  {
    "id": 2,
    "symbol": "EURUSD",
    "direction": "SELL",
    "pnl": -25.0,
    "pnl_pips": -250.0,
    "rr_achieved": -1.0,
    "outcome": "loss",
    "exit_reason": "sl_hit",
    "created_at": "2026-02-20T13:30:00Z"
  }
]
```

**Example:**

```bash
curl "http://localhost:8000/api/journal?playbook_id=1&outcome=win&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/journal/:id

Retrieve a full journal entry with complete indicator snapshots, management events, and market context.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The journal entry ID     |

**Response (200 OK):**

```json
{
  "id": 1,
  "symbol": "XAUUSD",
  "direction": "BUY",
  "lot_initial": 0.1,
  "open_price": 2760.0,
  "close_price": 2850.0,
  "sl_initial": 2712.5,
  "sl_final": 2840.0,
  "pnl": 90.0,
  "pnl_pips": 900.0,
  "rr_achieved": 1.89,
  "outcome": "win",
  "exit_reason": "tp_hit",
  "duration_seconds": 3600,
  "playbook_phase_at_entry": "entry_ready_long",
  "variables_at_entry": {
    "entry_price": 2760.0,
    "structure_break_price": 2780.0
  },
  "entry_snapshot": {
    "h4_rsi": {
      "values": { "value": 28.5 }
    },
    "h4_ema_200": {
      "values": { "value": 2650.0 }
    }
  },
  "exit_snapshot": {
    "h4_rsi": {
      "values": { "value": 55.2 }
    },
    "h4_ema_200": {
      "values": { "value": 2655.0 }
    }
  },
  "market_context": {
    "atr": 15.0,
    "session": "london",
    "trend": "bullish",
    "volatility": "normal"
  },
  "management_events": [
    {
      "rule_name": "breakeven_at_1rr",
      "action": "modify_sl",
      "details": {
        "new_sl": 2761.5,
        "triggered_at": "2026-02-20T12:30:00Z"
      }
    },
    {
      "rule_name": "trailing_stop",
      "action": "modify_sl",
      "details": {
        "new_sl": 2840.0,
        "triggered_at": "2026-02-20T12:55:00Z"
      }
    }
  ]
}
```

| Response Field              | Type     | Description                                        |
|-----------------------------|----------|----------------------------------------------------|
| `lot_initial`               | float    | Initial lot size                                   |
| `open_price`                | float    | Trade entry price                                  |
| `close_price`               | float    | Trade exit price                                   |
| `sl_initial`                | float    | Original stop loss level                           |
| `sl_final`                  | float    | Final stop loss (after modifications)              |
| `pnl`                       | float    | Profit/loss in account currency                    |
| `pnl_pips`                  | float    | Profit/loss in pips                                |
| `rr_achieved`               | float    | Risk-to-reward ratio achieved                      |
| `outcome`                   | string   | `"win"`, `"loss"`, or `"breakeven"`                |
| `exit_reason`               | string   | How the trade was closed (see table below)         |
| `duration_seconds`          | int      | Trade duration in seconds                          |
| `playbook_phase_at_entry`   | string   | The playbook phase when the trade was opened       |
| `variables_at_entry`        | object   | Playbook state variables at time of entry          |
| `entry_snapshot`            | object   | Indicator values at trade entry                    |
| `exit_snapshot`             | object   | Indicator values at trade exit                     |
| `market_context`            | object   | Market conditions at entry (ATR, session, trend)   |
| `management_events`         | array    | Chronological list of position management actions  |

**Exit Reasons:**

| Value        | Description                                  |
|--------------|----------------------------------------------|
| `tp_hit`     | Take profit target reached                   |
| `sl_hit`     | Stop loss triggered                          |
| `trailing`   | Trailing stop triggered                      |
| `timeout`    | Maximum holding time or bar limit reached    |
| `kill_switch`| Emergency kill switch activated               |
| `manual`     | User manually closed the trade               |

**Example:**

```bash
curl http://localhost:8000/api/journal/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/journal/analytics

Aggregate analytics across journal entries. Returns overall performance statistics with optional filtering.

**Query Parameters:**

| Parameter     | Type   | Required | Description                      |
|---------------|--------|----------|----------------------------------|
| `playbook_id` | int    | No       | Filter by playbook ID            |
| `strategy_id` | int    | No       | Filter by legacy strategy ID     |
| `symbol`      | string | No       | Filter by symbol                 |

**Response (200 OK):**

```json
{
  "total_trades": 50,
  "wins": 30,
  "losses": 18,
  "breakevens": 2,
  "win_rate": 60.0,
  "avg_pnl": 12.50,
  "total_pnl": 625.00,
  "avg_pips": 45.2,
  "avg_rr": 1.85,
  "best_trade": 150.00,
  "worst_trade": -45.00,
  "avg_duration_seconds": 5400,
  "avg_bars_held": 12.5,
  "exit_reasons": {
    "tp_hit": 25,
    "sl_hit": 15,
    "trailing": 8,
    "timeout": 2
  }
}
```

| Response Field          | Type   | Description                                 |
|-------------------------|--------|---------------------------------------------|
| `total_trades`          | int    | Total number of closed trades               |
| `wins`                  | int    | Number of winning trades                    |
| `losses`                | int    | Number of losing trades                     |
| `breakevens`            | int    | Number of breakeven trades                  |
| `win_rate`              | float  | Win percentage (0-100)                      |
| `avg_pnl`               | float  | Average profit/loss per trade               |
| `total_pnl`             | float  | Cumulative profit/loss                      |
| `avg_pips`              | float  | Average pips per trade                      |
| `avg_rr`                | float  | Average risk-to-reward ratio                |
| `best_trade`            | float  | Largest single-trade profit                 |
| `worst_trade`           | float  | Largest single-trade loss                   |
| `avg_duration_seconds`  | int    | Average trade duration in seconds           |
| `avg_bars_held`         | float  | Average number of bars a trade was held     |
| `exit_reasons`          | object | Count of trades by exit reason              |

**Example:**

```bash
curl "http://localhost:8000/api/journal/analytics?playbook_id=1" \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/journal/analytics/conditions

Per-condition win rate analysis from entry conditions stored in journal entries. Useful for identifying which conditions contribute to wins and which underperform.

**Query Parameters:**

| Parameter     | Type | Required | Description              |
|---------------|------|----------|--------------------------|
| `playbook_id` | int  | No       | Filter by playbook ID    |

**Response (200 OK):**

```json
[
  {
    "condition": "h4_structure_bullish",
    "total": 30,
    "wins": 22,
    "losses": 8,
    "win_rate": 73.3
  },
  {
    "condition": "rsi_oversold",
    "total": 25,
    "wins": 10,
    "losses": 15,
    "win_rate": 40.0
  },
  {
    "condition": "volume_above_avg",
    "total": 20,
    "wins": 15,
    "losses": 5,
    "win_rate": 75.0
  }
]
```

| Response Field | Type   | Description                                          |
|----------------|--------|------------------------------------------------------|
| `condition`    | string | The entry condition identifier                       |
| `total`        | int    | Total trades where this condition was active         |
| `wins`         | int    | Trades won with this condition                       |
| `losses`       | int    | Trades lost with this condition                      |
| `win_rate`     | float  | Win percentage for this condition (0-100)            |

**Example:**

```bash
curl "http://localhost:8000/api/journal/analytics/conditions?playbook_id=1" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Signals

Signals are generated by strategies and playbooks when entry conditions are met. In `signal_only` and `semi_auto` modes, signals require manual approval before execution.

---

### GET /api/signals

List signals with optional filtering.

**Query Parameters:**

| Parameter     | Type   | Required | Description                                              |
|---------------|--------|----------|----------------------------------------------------------|
| `strategy_id` | int    | No       | Filter by strategy ID                                    |
| `status`      | string | No       | Filter by status: `pending`, `approved`, `rejected`, `executed`, `expired` |
| `limit`       | int    | No       | Max entries to return (default: 50)                      |
| `offset`      | int    | No       | Pagination offset (default: 0)                           |

**Response (200 OK):**

```json
[
  {
    "id": 1,
    "strategy_id": 1,
    "symbol": "XAUUSD",
    "direction": "LONG",
    "entry_price": 2750.00,
    "sl": 2730.00,
    "tp": 2790.00,
    "lot": 0.1,
    "status": "pending",
    "created_at": "2026-02-20T14:00:00Z",
    "expires_at": "2026-02-20T18:00:00Z"
  }
]
```

**Example:**

```bash
curl "http://localhost:8000/api/signals?status=pending&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

---

### POST /api/signals/:id/approve

Approve a pending signal for execution. The trade will be sent to MT5 via the ZeroMQ bridge.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The signal ID            |

**Response (200 OK):**

```json
{
  "status": "approved",
  "trade_id": 1
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/signals/1/approve \
  -H "Authorization: Bearer $TOKEN"
```

---

### POST /api/signals/:id/reject

Reject a pending signal. The signal will be marked as rejected and no trade will be opened.

**Path Parameters:**

| Parameter | Type | Description              |
|-----------|------|--------------------------|
| `id`      | int  | The signal ID            |

**Response (200 OK):**

```json
{
  "status": "rejected"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/signals/1/reject \
  -H "Authorization: Bearer $TOKEN"
```

---

## Trades

---

### GET /api/trades

List historical trades with optional filtering.

**Query Parameters:**

| Parameter     | Type   | Required | Description                      |
|---------------|--------|----------|----------------------------------|
| `strategy_id` | int    | No       | Filter by strategy ID            |
| `symbol`      | string | No       | Filter by symbol                 |
| `limit`       | int    | No       | Max entries to return            |
| `offset`      | int    | No       | Pagination offset                |

**Response (200 OK):**

```json
[
  {
    "id": 1,
    "strategy_id": 1,
    "symbol": "XAUUSD",
    "direction": "BUY",
    "lot": 0.1,
    "open_price": 2750.00,
    "close_price": 2790.00,
    "sl": 2730.00,
    "tp": 2790.00,
    "pnl": 40.00,
    "status": "closed",
    "opened_at": "2026-02-20T14:05:00Z",
    "closed_at": "2026-02-20T16:30:00Z"
  }
]
```

**Example:**

```bash
curl "http://localhost:8000/api/trades?symbol=XAUUSD&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/trades/open

Returns currently open positions from MT5 via the ZeroMQ bridge.

**Response (200 OK):**

```json
[
  {
    "ticket": 123456,
    "symbol": "XAUUSD",
    "direction": "BUY",
    "lot": 0.1,
    "open_price": 2750.00,
    "current_price": 2765.00,
    "sl": 2730.00,
    "tp": 2790.00,
    "pnl": 15.00,
    "opened_at": "2026-02-20T14:05:00Z"
  }
]
```

**Example:**

```bash
curl http://localhost:8000/api/trades/open \
  -H "Authorization: Bearer $TOKEN"
```

---

## Market Data

---

### GET /api/market/:symbol

Returns the current tick data for a given symbol from MT5.

**Path Parameters:**

| Parameter | Type   | Description                       |
|-----------|--------|-----------------------------------|
| `symbol`  | string | Trading symbol (e.g., `XAUUSD`)   |

**Response (200 OK):**

```json
{
  "symbol": "XAUUSD",
  "bid": 2750.50,
  "ask": 2751.00,
  "spread": 0.50,
  "time": "2026-02-20T14:30:00Z"
}
```

**Example:**

```bash
curl http://localhost:8000/api/market/XAUUSD \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/account

Returns the MT5 account information including balance, equity, and margin.

**Response (200 OK):**

```json
{
  "balance": 10000.00,
  "equity": 10150.00,
  "margin": 250.00,
  "free_margin": 9900.00,
  "margin_level": 4060.0,
  "currency": "USD"
}
```

**Example:**

```bash
curl http://localhost:8000/api/account \
  -H "Authorization: Bearer $TOKEN"
```

---

### GET /api/indicators

Returns the full indicator catalog available for use in strategies and playbooks. Each indicator includes its parameters and output values.

**Response (200 OK):**

```json
[
  {
    "name": "RSI",
    "description": "Relative Strength Index",
    "params": {
      "period": { "type": "int", "default": 14, "min": 2, "max": 100 }
    },
    "outputs": {
      "value": { "type": "float", "range": [0, 100] }
    }
  },
  {
    "name": "EMA",
    "description": "Exponential Moving Average",
    "params": {
      "period": { "type": "int", "default": 20, "min": 1, "max": 500 }
    },
    "outputs": {
      "value": { "type": "float" }
    }
  },
  {
    "name": "ATR",
    "description": "Average True Range",
    "params": {
      "period": { "type": "int", "default": 14, "min": 1, "max": 100 }
    },
    "outputs": {
      "value": { "type": "float" }
    }
  }
]
```

The full catalog includes 13 indicators. Use this endpoint to discover available indicators and their parameter schemas when building strategies or playbooks programmatically.

**Example:**

```bash
curl http://localhost:8000/api/indicators \
  -H "Authorization: Bearer $TOKEN"
```

---

## Settings

---

### GET /api/settings

Retrieve the current agent settings.

**Response (200 OK):**

```json
{
  "max_lot": 0.1,
  "max_daily_trades": 10,
  "max_daily_loss": 500.00,
  "max_concurrent_trades": 3,
  "default_autonomy": "signal_only",
  "allowed_symbols": ["XAUUSD", "EURUSD", "GBPUSD"],
  "trading_hours": {
    "start": "08:00",
    "end": "20:00",
    "timezone": "UTC"
  }
}
```

**Example:**

```bash
curl http://localhost:8000/api/settings \
  -H "Authorization: Bearer $TOKEN"
```

---

### PUT /api/settings

Update agent settings. Only provided fields are updated.

**Request:**

```json
{
  "max_lot": 0.1,
  "max_daily_trades": 10,
  "max_daily_loss": 500.00,
  "max_concurrent_trades": 3,
  "default_autonomy": "signal_only",
  "allowed_symbols": ["XAUUSD", "EURUSD", "GBPUSD"],
  "trading_hours": {
    "start": "08:00",
    "end": "20:00",
    "timezone": "UTC"
  }
}
```

**Response (200 OK):**

```json
{
  "status": "updated"
}
```

**Example:**

```bash
curl -X PUT http://localhost:8000/api/settings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_lot": 0.2, "max_daily_trades": 15}'
```

---

## Kill Switch

The kill switch is an emergency mechanism that immediately closes all open positions and halts all trading activity.

---

### POST /api/kill-switch

Activate the kill switch. This will:

1. Cancel all pending signals.
2. Close all open positions in MT5.
3. Disable all active strategies and playbooks.
4. Halt the trading engine until deactivated.

**Response (200 OK):**

```json
{
  "status": "activated",
  "positions_closed": 3,
  "strategies_disabled": 2,
  "playbooks_disabled": 1
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/kill-switch \
  -H "Authorization: Bearer $TOKEN"
```

---

### POST /api/kill-switch/deactivate

Deactivate the kill switch and resume normal operation. Strategies and playbooks must be re-enabled manually.

**Response (200 OK):**

```json
{
  "status": "deactivated"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/kill-switch/deactivate \
  -H "Authorization: Bearer $TOKEN"
```

---

## WebSocket

The WebSocket endpoint provides real-time streaming of tick data, signals, and trade events.

### Connection

```
ws://localhost:8000/api/ws?token=<JWT_TOKEN>
```

Authentication is required via the `token` query parameter. The connection will be rejected with a `403` if the token is invalid or expired.

**JavaScript Example:**

```javascript
const ws = new WebSocket('ws://localhost:8000/api/ws?token=' + accessToken);

ws.onopen = () => {
  console.log('Connected to Trade Agent WebSocket');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  switch (message.type) {
    case 'tick':
      handleTick(message.data);
      break;
    case 'signal':
      handleSignal(message.data);
      break;
    case 'trade':
      handleTrade(message.data);
      break;
  }
};

ws.onclose = (event) => {
  console.log('Disconnected:', event.code, event.reason);
};
```

### Event Types

#### Tick Event

Pushed on every price update from MT5.

```json
{
  "type": "tick",
  "data": {
    "symbol": "XAUUSD",
    "bid": 2750.50,
    "ask": 2751.00,
    "time": "2026-02-20T14:30:00.123Z"
  }
}
```

#### Signal Event

Pushed when a strategy or playbook generates a new signal.

```json
{
  "type": "signal",
  "data": {
    "id": 1,
    "strategy_id": 1,
    "playbook_id": null,
    "direction": "LONG",
    "symbol": "XAUUSD",
    "entry_price": 2750.00,
    "sl": 2730.00,
    "tp": 2790.00,
    "lot": 0.1,
    "status": "pending",
    "created_at": "2026-02-20T14:00:00Z"
  }
}
```

#### Trade Event

Pushed when a trade is opened, modified, or closed.

```json
{
  "type": "trade",
  "data": {
    "id": 1,
    "ticket": 123456,
    "direction": "BUY",
    "symbol": "XAUUSD",
    "lot": 0.1,
    "open_price": 2750.00,
    "sl": 2730.00,
    "tp": 2790.00,
    "status": "open",
    "pnl": 0.00,
    "opened_at": "2026-02-20T14:05:00Z"
  }
}
```

---

## Error Responses

All endpoints return consistent error responses in the following format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### HTTP Status Codes

| Code | Meaning                | Common Causes                                    |
|------|------------------------|--------------------------------------------------|
| 400  | Bad Request            | Invalid request body, missing required fields    |
| 401  | Unauthorized           | Missing or expired JWT token                     |
| 403  | Forbidden              | Insufficient permissions                         |
| 404  | Not Found              | Resource does not exist                          |
| 409  | Conflict               | Duplicate resource (e.g., username already taken)|
| 422  | Unprocessable Entity   | Validation error (invalid field values)          |
| 500  | Internal Server Error  | Server-side error (MT5 disconnected, AI failure) |
| 503  | Service Unavailable    | Kill switch active, MT5 not connected            |

### Authentication Errors

```json
// Missing token
{
  "detail": "Not authenticated"
}

// Expired token
{
  "detail": "Token has expired"
}

// Invalid token
{
  "detail": "Could not validate credentials"
}
```

### Validation Errors

```json
{
  "detail": [
    {
      "loc": ["body", "username"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Rate Limits

AI-powered endpoints (`POST /api/strategies`, `POST /api/playbooks`, `POST /api/strategies/:id/chat`, `POST /api/playbooks/:id/refine`) are subject to Claude API rate limits. If the rate limit is exceeded, the server returns a `429 Too Many Requests` response.

---

## Architecture Notes

- **Backend:** FastAPI (Python) with async/await, running on port 8000
- **MT5 Bridge:** ZeroMQ REP socket on port 5555 (commands), PUB socket on port 5556 (tick stream)
- **Database:** SQLite for strategies, playbooks, journal, signals, and trades
- **AI Integration:** Claude Opus for playbook building, Claude Sonnet for refinement
- **Dashboard:** React + Vite + Tailwind on port 5173 (dev mode)
