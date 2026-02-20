# Trade Agent Architecture

AI-powered multi-timeframe trading agent with natural language strategy building, MT5 execution via ZeroMQ, and three autonomy levels.

## High-Level Overview

```
+------------------+       ZMQ REQ/REP        +------------------+
|                  | <------- port 5555 -----> |                  |
|  FastAPI Backend |                           |  MT5 Expert      |
|  (Python)        | <------- port 5556 ----   |  Advisor (MQL5)  |
|  Port 8000       |       ZMQ PUB/SUB (ticks) |                  |
+------------------+                           +------------------+
        |
        | HTTP + WebSocket
        v
+------------------+
|  React Dashboard |
|  (Vite + TS)     |
|  Port 5173       |
+------------------+
```

The system has three main layers:

1. **MT5 Expert Advisor** -- runs inside MetaTrader 5, provides market data and trade execution via ZeroMQ sockets
2. **FastAPI Backend** -- Python application that manages strategies, playbooks, risk, and AI-powered NL parsing
3. **React Dashboard** -- browser-based UI for monitoring signals, managing strategies, and controlling the agent

---

## System Components

### 1. FastAPI Backend (`agent/api/main.py`)

The main application entry point. Uses FastAPI's lifespan context manager to initialize and wire all components at startup.

**Startup sequence (lifespan):**

```
Database.connect()
  -> ZMQBridge.connect()
    -> DataManager(bridge)
      -> AIService()
        -> RiskManager()
          -> StrategyEngine(data_manager)
            -> TradeExecutor(bridge, risk_manager)
              -> PlaybookEngine(data_manager)
                -> JournalWriter(db, data_manager)
```

All components are wired via async callbacks defined in `api/main.py` and stored in a global `app_state` dict. Route handlers access components through `app_state`:

```python
app_state = {
    "db": Database,
    "bridge": ZMQBridge,
    "data_manager": DataManager,
    "ai_service": AIService,
    "risk_manager": RiskManager,
    "strategy_engine": StrategyEngine,
    "trade_executor": TradeExecutor,
    "playbook_engine": PlaybookEngine,
    "journal_writer": JournalWriter,
    "mt5_connected": bool,
}
```

**Callback wiring at startup:**

- `strategy_engine.on_signal(on_signal)` -- saves signal to DB, runs risk check, executes via trade executor, broadcasts to WebSocket
- `trade_executor.on_trade(on_trade)` -- saves trade to DB, broadcasts to WebSocket
- `data_manager.on_bar_close(strategy_engine.evaluate_on_bar_close)` -- triggers strategy evaluation on every new bar
- `data_manager.on_bar_close(playbook_engine.evaluate_on_bar_close)` -- triggers playbook evaluation on every new bar
- `playbook_engine.on_signal(on_playbook_signal)` -- saves playbook signals to DB, broadcasts
- `playbook_engine.on_trade_action(on_playbook_trade_action)` -- risk check, MT5 execution, journal entry, WebSocket broadcast
- `playbook_engine.on_management_event(on_playbook_management)` -- modifies SL/TP, trails, partial closes
- `playbook_engine.on_state_change(on_playbook_state_change)` -- persists playbook state to DB
- `bridge.on_tick(on_tick)` -- forwards ticks to data manager and WebSocket

**Telegram notifications:** Signal, trade, and management event callbacks also call `notify_signal()`, `notify_trade_opened()`, and `notify_management_event()` from `agent/notifications.py` (only fires if `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in `.env`).

**API routes:**

| Router | Prefix | Purpose |
|--------|--------|---------|
| `auth` | `/api/auth/` | Register, login (JWT) |
| `strategies` | `/api/strategies/` | CRUD strategies, parse NL, chat |
| `playbooks` | `/api/playbooks/` | CRUD playbooks, build from NL, refine |
| `signals` | `/api/signals/` | List signals, approve/reject |
| `trades` | `/api/trades/` | List trades, close positions |
| `market` | `/api/market/` | Tick data, indicators, account info |
| `settings` | `/api/settings/` | Risk limits, kill switch |
| `journal` | `/api/journal/` | Journal entries, analytics |
| `ws` | `/api/ws` | WebSocket for real-time events |
| `health` | `/api/health` | Health check |

**Offline mode:** If MT5 is not connected at startup, the backend runs in offline mode -- strategy parsing, playbook building, and dashboard access still work, but no live market data or trade execution.

---

### 2. ZMQ Bridge (`agent/bridge.py`)

The communication layer between Python and the MT5 Expert Advisor. Uses two ZeroMQ sockets:

**REQ socket (port 5555):** Request/reply pattern for commands.
- Protected by an `asyncio.Lock` to prevent concurrent sends (ZMQ REQ/REP is strictly sequential)
- 5-second send/receive timeout (`ZMQ_RCVTIMEO`, `ZMQ_SNDTIMEO`)
- Auto-reconnect on timeout: closes the stale socket, creates a new one, reconnects
- `ZMQ_LINGER = 0` so shutdown never blocks

**SUB socket (port 5556):** Subscribe pattern for tick stream.
- Subscribes to all messages (`subscribe(b"")`)
- 1-second receive timeout for clean shutdown detection
- Runs in a background `asyncio.Task` via `start_tick_listener()`

**Supported commands:**

| Command | Method | Description |
|---------|--------|-------------|
| `GET_TICK` | `get_tick(symbol)` | Current bid/ask/spread for a symbol |
| `GET_BARS` | `get_bars(symbol, timeframe, count)` | OHLCV bars |
| `GET_INDICATOR` | `get_indicator(symbol, tf, name, params, count)` | Indicator values (multi-buffer) |
| `OPEN_ORDER` | `open_order(symbol, type, lot, sl, tp)` | Market order execution |
| `CLOSE_ORDER` | `close_order(ticket)` | Close position by ticket |
| `MODIFY_ORDER` | `modify_order(ticket, sl, tp)` | Modify SL/TP on open position |
| `GET_POSITIONS` | `get_positions()` | All open positions |
| `GET_ACCOUNT` | `get_account()` | Account balance/equity/margin |
| `GET_HISTORY` | `get_history(from_date, to_date)` | Historical deals |
| `SUBSCRIBE` | `subscribe_symbols(symbols)` | Subscribe to tick stream for symbols |
| `PING` | `ping()` | Connectivity check |

**Protocol format:**

```
Request:  {"command": "CMD", "params": {...}}
Response: {"success": true, "data": {...}}
          {"success": false, "error": "..."}
```

**Partial close:** Implemented as opening an opposite-direction position for the partial lot size (MT5 netting accounts don't support native partial close).

---

### 3. Data Manager (`agent/data_manager.py`)

Manages in-memory market data buffers and bar close detection.

**In-memory buffers:**

| Buffer | Key | Type | Max Size |
|--------|-----|------|----------|
| Bars | `(symbol, timeframe)` | `list[Bar]` | 200 per key |
| Indicators | `(symbol, timeframe, indicator_id)` | `IndicatorValue` | Latest cached |
| Ticks | `symbol` | `Tick` | Latest per symbol |

**Bar close detection:**
1. On every tick, checks all subscribed timeframes for the tick's symbol
2. Fetches the latest 2 bars from MT5 via bridge
3. Compares `latest.time` against `_last_bar_time[(symbol, tf)]`
4. If newer, fires all `_bar_close_callbacks` with `(symbol, timeframe)`
5. First detection after initialization is skipped (prevents false trigger)

**Indicator refresh (`fetch_indicator`):**
- Fetches indicator values from MT5 via bridge (returns dict of `buffer_name -> list[float]`)
- Takes `index 0` (current bar) as the latest value for each buffer
- Caches as `IndicatorValue` keyed by `(symbol, timeframe, indicator_id)`

**Market snapshot (`get_snapshot`):**
- Returns a `MarketSnapshot` containing current tick, bar buffer, and all cached indicators for a symbol/timeframe pair

**Subscriptions:**
- Components call `data_manager.subscribe(symbol, timeframes)` to register interest
- `initialize(symbol, timeframes, bar_count)` pre-fetches historical bars and sets initial `_last_bar_time`

---

### 4. Strategy Engine (`agent/strategy_engine.py`) -- Legacy

The original rule-based strategy evaluator. Runs on bar close events alongside the playbook engine.

**Evaluation flow:**

1. `evaluate_on_bar_close(symbol, timeframe)` is called by the data manager
2. For each enabled strategy that uses this symbol/timeframe:
   - Refreshes all indicator values for the timeframe
   - Evaluates 4 condition groups: `entry_long`, `entry_short`, `exit_long`, `exit_short`
3. Each condition group is AND/OR of rules
4. Each rule compares an indicator field against a value, another indicator, or price

**Rule types:**

- **Filter** (`type: "filter"`): Continuous condition on higher timeframe (e.g., H4 RSI < 30). Uses standard operators: `<`, `>`, `<=`, `>=`, `==`.
- **Trigger** (`type: "trigger"`): Momentary cross event on lower timeframe (e.g., M15 Stochastic crosses above 20). Uses `cross_above` / `cross_below` fields.

**Cross detection:**
- Stores previous bar's indicator values in `_prev_values[(strategy_id, indicator_id)]`
- `cross_above`: `prev <= threshold AND current > threshold`
- `cross_below`: `prev >= threshold AND current < threshold`

**Signal emission:**
- Creates a `Signal` with direction, conditions snapshot, and price
- Fires all `_signal_callbacks` (wired to `on_signal` in `api/main.py`)

---

### 5. Playbook Engine (`agent/playbook_engine.py`) -- New

A deterministic state machine runner. Each playbook defines phases with transitions, actions, and position management rules. Zero AI calls at runtime.

**Core concepts:**

- **`PlaybookInstance`**: Runtime state for a single playbook on a single symbol. Contains the playbook config, current phase, variables, and open position data.
- **`PlaybookEngine`**: Manages all active instances and evaluates them on bar close.

**Phase state machine:**

Each phase defines:
- `evaluate_on`: list of timeframes that trigger evaluation
- `transitions`: ordered list of transitions, each with conditions, target phase, priority, and actions
- `timeout`: max bars in phase before auto-transition
- `position_management`: rules for modifying SL/TP/trailing/partial close while in this phase
- `on_trade_closed`: auto-transition target when a trade closes

**Evaluation flow per instance:**

1. Check if this timeframe is in the current phase's `evaluate_on` list
2. Refresh indicators for the timeframe
3. Build `ExpressionContext` with indicators, prev indicators, variables, price, trade data, risk params
4. Increment bar counters
5. Check phase timeout (auto-transition if exceeded)
6. Evaluate transitions sorted by priority (descending) -- first match wins
7. Execute transition actions (set variables, open/close trades, log)
8. Transition to target phase
9. If no transition matched, evaluate position management rules
10. Persist state to DB

**Actions on transition:**

- `set_var` + `expr`: evaluate expression and store in variables
- `open_trade`: emit signal + trade action for execution
- `close_trade`: emit close signal
- `log`: log a message

**Position management rules:**

- `modify_sl`: set SL to an expression value
- `modify_tp`: set TP to an expression value
- `trail_sl`: trail SL at a distance (only moves in profitable direction)
- `partial_close`: close a percentage of the position
- `once`: if true, rule fires only once per phase entry

**Expression evaluation (`agent/playbook_eval.py`):**

- Evaluates conditions and expressions using an `ExpressionContext`
- Supports accessing indicators (`indicators.h4_rsi.value`), variables (`variables.initial_sl`), price, and trade data
- Supports arithmetic, comparisons, and cross detection

**Trade lifecycle notifications:**

- `notify_trade_opened(playbook_id, ticket, direction, price, sl, tp, lot)`: updates instance state with open position data
- `notify_trade_closed(playbook_id)`: clears open ticket, triggers `on_trade_closed` transition if defined

---

### 6. Trade Executor (`agent/trade_executor.py`)

Routes approved signals to MT5 based on autonomy level.

**Autonomy levels:**

| Level | Behavior |
|-------|----------|
| `signal_only` | Save signal as pending, send notification. No trade execution. |
| `semi_auto` | Execute trade on MT5 (same as full_auto in current implementation). |
| `full_auto` | Execute trade on MT5. Auto-pause strategy on drawdown breach. |

**Signal processing flow:**

1. Risk check via `RiskManager.check_signal()`
2. If rejected: set signal status to `REJECTED`, log reason. If action is `kill`, disable the strategy.
3. If approved and `signal_only`: set status to `PENDING`, fire notification callbacks
4. If approved and `semi_auto`/`full_auto`: call `bridge.open_order()`, create `Trade` record, fire trade callbacks

**Exit signal handling:**
- Gets all open positions from MT5
- Closes all positions matching the signal's symbol and direction
- Status becomes `EXECUTED` if any closed, `EXPIRED` if none found

**Kill switch (`execute_kill_switch`):**
- Closes ALL open positions regardless of strategy or symbol
- Returns count of successfully closed positions

**Position modification:**
- `modify_position(ticket, sl, tp)`: direct pass-through to `bridge.modify_order()`
- `partial_close(ticket, pct)`: calculates close lot from position's current lot, opens opposite-direction order

---

### 7. Risk Manager (`agent/risk_manager.py`)

Enforces per-strategy and global risk limits before trade execution.

**Risk checks (in order):**

| # | Check | Scope | Action on Fail |
|---|-------|-------|----------------|
| 1 | Kill switch active | Global | Block |
| 2 | Exit signals | -- | Always pass |
| 3 | Signal-only mode | Strategy | Always pass |
| 4 | Max lot > 0 | Strategy | Block |
| 5 | Max daily trades | Strategy | Block |
| 6 | Max open positions | Strategy | Block |
| 7 | Total lot exposure | Global | Block |
| 8 | Drawdown (strategy) | Strategy | Block or Kill (kill for full_auto) |
| 9 | Drawdown (global) | Global | Kill |

**Default global limits:**
- `max_total_lots`: 1.0
- `max_account_drawdown_pct`: 10.0%
- `daily_loss_limit`: $500

**Daily trade counter:** Resets automatically when the date changes. Tracked per `strategy_id`.

**Drawdown calculation:** `(initial_balance - current_equity) / initial_balance * 100`

**RiskDecision actions:**
- `pass`: signal approved
- `block`: signal rejected, strategy continues
- `kill`: signal rejected, strategy auto-paused

---

### 8. Journal Writer (`agent/journal_writer.py`) -- New

Captures full trade context for learning and refinement of playbooks.

**On trade open (`on_trade_opened`):**
- Captures full indicator snapshot (all indicators configured in the playbook)
- Captures market context: ATR, session (asian/london/overlap/newyork), volatility, trend, spread
- Creates `TradeJournalEntry` with entry data, variables at entry, playbook phase at entry
- Stores mapping: `ticket -> journal_id` for later closure

**On trade close (`on_trade_closed`):**
- Computes duration (seconds), PnL, PnL in pips, R:R achieved, outcome (win/loss/breakeven)
- Captures exit indicator snapshot
- Updates journal entry with all exit data

**On management event (`on_management_event`):**
- Appends a `ManagementEvent` to the journal entry's event list
- Tracks: rule name, action type, details, phase, timestamp
- Updates `lot_remaining` for partial closes

**Market context detection:**

| Field | Method |
|-------|--------|
| `session` | UTC hour: 0-8 asian, 8-12 london, 12-16 overlap, 16-21 newyork |
| `atr` | Cached ATR indicator (checks H1, H4, M15 in order) |
| `trend` | SMC Structure indicator if available (bullish/bearish/ranging) |
| `spread` | From latest tick |

**Pip calculation:** Uses per-symbol pip values (e.g., XAUUSD = 0.1, EURUSD = 0.0001). Pip direction inverted for SELL trades.

---

### 9. AI Service (`agent/ai_service.py`)

Interfaces with Claude API for strategy parsing, playbook building, and refinement.

**Methods:**

| Method | Model | Purpose |
|--------|-------|---------|
| `parse_strategy(nl)` | Claude Opus | NL strategy description -> `StrategyConfig` JSON |
| `build_playbook(nl)` | Claude Opus | NL + indicator skills -> `PlaybookConfig` JSON |
| `refine_playbook(config, journal, messages)` | Claude Sonnet | Config + journal analytics + conversation -> analysis + optional `<playbook_update>` |
| `chat_strategy(config, messages)` | Claude Sonnet | Multi-turn conversation about a strategy |
| `explain_signal(...)` | Claude Sonnet | Generate 2-3 sentence signal explanation |

**Skills loading:**

1. `_identify_indicators(text)`: scans NL text for indicator keywords (RSI, EMA, MACD, Bollinger, SMC, etc.)
2. Always includes ATR (used for SL/TP sizing)
3. Loads matching `.md` files from `agent/indicators/skills/` directory
4. Always loads `_combinations.md` guide
5. Skills content is injected into the system prompt alongside the indicator catalog

**Indicator catalog:** Loaded from `agent/indicators/catalog.json` -- defines available indicators with their names, parameters, and buffer outputs.

**Playbook refinement flow:**
- Includes current playbook config, journal analytics (win rate, avg PnL, etc.), per-condition win rates, and recent trade samples in the system prompt
- AI response may include a `<playbook_update>...</playbook_update>` XML tag containing updated config JSON
- If present, the update is parsed and returned as `updated_config`

**Build sessions:** Every `build_playbook` call records a `build_sessions` entry in the DB with NL input, skills used, model, token usage, and duration.

---

### 10. MT5 Expert Advisor (`mt5/TradeAgent.mq5`)

MQL5 Expert Advisor that runs inside MetaTrader 5 and acts as the ZeroMQ server.

**Socket architecture:**
- **REP socket (port 5555):** Bound on `tcp://*:5555`. Polled via `OnTimer()` at 1ms intervals. Non-blocking receive with 1ms timeout.
- **PUB socket (port 5556):** Bound on `tcp://*:5556`. Publishes tick data for all subscribed symbols on `OnTick()` and `OnBookEvent()`.

**Indicator handling:**

Built-in indicators are mapped to native MQL5 functions:

| Name | MQL5 Function | Buffers |
|------|---------------|---------|
| RSI | `iRSI()` | `value` |
| EMA | `iMA(MODE_EMA)` | `value` |
| SMA | `iMA(MODE_SMA)` | `value` |
| MACD | `iMACD()` | `macd`, `signal` |
| STOCHASTIC | `iStochastic()` | `k`, `d` |
| BOLLINGER/BB | `iBands()` | `middle`, `upper`, `lower` |
| ATR | `iATR()` | `value` |
| ADX | `iADX()` | `adx`, `plus_di`, `minus_di` |
| CCI | `iCCI()` | `value` |
| WILLIAMSR/WPR | `iWPR()` | `value` |

Custom indicators use `iCustom()` with configurable params:
- `path`: indicator path (defaults to name if not specified)
- `buffers`: number of buffers to read
- `buffer_names`: array of names for each buffer
- `p1`-`p4`: integer inputs, `d1`-`d2`: double inputs

**Indicator handle caching:**
- Up to 50 handles cached by key: `"SYMBOL|TF|NAME|PARAMS_HASH"`
- LRU eviction when cache is full (oldest entry released)
- All handles released on EA deinitialization

**Trade execution:**
- Uses `CTrade` class with 10-point deviation, IOC filling, synchronous mode
- Validates lot against symbol min/max/step, normalizes SL/TP to digit precision
- Returns ticket number on success, retcode + description on failure

**Tick streaming:**
- `OnTick()`: publishes JSON tick data for all subscribed symbols
- `OnBookEvent()`: secondary tick source for cross-symbol data (via `MarketBookAdd()`)
- Tick JSON format: `{"symbol": "XAUUSD", "bid": 2345.67, "ask": 2345.89, "timestamp": "2026-02-20T10:30:00"}`

---

## Data Flow Diagrams

### Tick Flow

```
MT5 OnTick() / OnBookEvent()
  |
  v
ZMQ PUB socket (port 5556)
  |
  v
Bridge._tick_loop() [asyncio Task]
  |
  +-- on_tick callbacks
       |
       +-- DataManager.on_tick(tick)
       |     |
       |     +-- _ticks[symbol] = tick
       |     +-- for each subscribed timeframe:
       |           _check_new_bar(symbol, tf)
       |             |
       |             +-- GET_BARS via bridge (2 bars)
       |             +-- if latest.time > _last_bar_time:
       |                   fire bar_close_callbacks(symbol, tf)
       |                     |
       |                     +-- StrategyEngine.evaluate_on_bar_close()
       |                     +-- PlaybookEngine.evaluate_on_bar_close()
       |
       +-- broadcast_tick() [WebSocket]
```

### Signal Flow (Strategy Engine)

```
StrategyEngine.evaluate_on_bar_close(symbol, tf)
  |
  +-- Refresh indicators via DataManager
  +-- Evaluate 4 condition groups (entry_long, exit_long, entry_short, exit_short)
  +-- If conditions met: _emit_signal()
        |
        v
on_signal callback (api/main.py)
  |
  +-- db.create_signal(signal)
  +-- RiskManager.check_signal()
  |     |
  |     +-- Returns RiskDecision (approved/blocked/kill)
  |
  +-- TradeExecutor.process_signal()
  |     |
  |     +-- signal_only: save as pending, notify
  |     +-- semi_auto/full_auto: Bridge.open_order()
  |           |
  |           +-- on_trade callback -> db.create_trade()
  |
  +-- db.update_signal_status()
  +-- broadcast_signal() [WebSocket]
```

### Signal Flow (Playbook Engine)

```
PlaybookEngine.evaluate_on_bar_close(symbol, tf)
  |
  +-- For each active PlaybookInstance:
        |
        +-- Refresh indicators
        +-- Build ExpressionContext
        +-- Check phase timeout
        +-- Evaluate transitions (priority order)
        |     |
        |     +-- If transition matches:
        |           Execute actions (set_var, open_trade, close_trade, log)
        |           Transition to target phase
        |
        +-- If no transition: evaluate position management rules
        +-- Persist state to DB
```

**Trade action from playbook:**

```
PlaybookEngine._handle_open_trade()
  |
  +-- Emit signal via on_signal callbacks
  |     -> db.create_signal() -> broadcast_signal() [WebSocket]
  |
  +-- Emit trade_data via on_trade_action callbacks
        |
        v
on_playbook_trade_action (api/main.py)
  |
  +-- RiskManager.check_signal()
  +-- Bridge.open_order(symbol, direction, lot, sl, tp)
  +-- db.create_trade()
  +-- PlaybookEngine.notify_trade_opened()
  +-- JournalWriter.on_trade_opened()
  +-- broadcast_trade() [WebSocket]
```

### Management Event Flow

```
PlaybookEngine._evaluate_management()
  |
  +-- For each position_management rule in current phase:
        |
        +-- Evaluate condition
        +-- If matched:
              |
              +-- modify_sl/modify_tp/trail_sl/partial_close
              +-- Emit via on_management_event callbacks
                    |
                    v
on_playbook_management (api/main.py)
  |
  +-- TradeExecutor.modify_position() or .partial_close()
  +-- JournalWriter.on_management_event()
```

---

## Database Schema

SQLite database at `data/trade_agent.db` with WAL journal mode.

### Tables

#### `strategies`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Strategy display name |
| description_nl | TEXT | Original natural language description |
| config_json | TEXT | Full `StrategyConfig` as JSON |
| autonomy | TEXT | `signal_only`, `semi_auto`, `full_auto` |
| enabled | INTEGER | 0 or 1 |
| risk_json | TEXT | `RiskConfig` as JSON |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-set |

#### `signals`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| strategy_id | INTEGER FK | References strategies.id |
| playbook_db_id | INTEGER | References playbooks.id (added via migration) |
| strategy_name | TEXT | Denormalized for display |
| symbol | TEXT | Trading symbol (e.g., XAUUSD) |
| direction | TEXT | `LONG`, `SHORT`, `EXIT_LONG`, `EXIT_SHORT` |
| conditions_snapshot | TEXT | JSON snapshot of indicator values at signal time |
| ai_reasoning | TEXT | AI-generated explanation or risk rejection reason |
| status | TEXT | `pending`, `executed`, `rejected`, `expired` |
| price_at_signal | REAL | Mid price at signal time |
| playbook_phase | TEXT | Phase name when signal was generated (added via migration) |
| created_at | TIMESTAMP | Auto-set |

#### `trades`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| signal_id | INTEGER FK | References signals.id |
| strategy_id | INTEGER FK | References strategies.id |
| playbook_db_id | INTEGER | References playbooks.id (added via migration) |
| journal_id | INTEGER | References trade_journal.id (added via migration) |
| symbol | TEXT | Trading symbol |
| direction | TEXT | `BUY` or `SELL` |
| lot | REAL | Position size |
| open_price | REAL | Entry price |
| close_price | REAL | Exit price (null if open) |
| sl | REAL | Stop loss |
| tp | REAL | Take profit |
| pnl | REAL | Profit/loss |
| ticket | INTEGER | MT5 position ticket |
| open_time | TIMESTAMP | Entry time |
| close_time | TIMESTAMP | Exit time (null if open) |

#### `playbooks`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Playbook display name |
| description_nl | TEXT | Original NL description |
| config_json | TEXT | Full `PlaybookConfig` as JSON |
| autonomy | TEXT | `signal_only`, `semi_auto`, `full_auto` |
| enabled | INTEGER | 0 or 1 |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-set |

#### `playbook_state`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| playbook_id | INTEGER FK | References playbooks.id |
| symbol | TEXT | Symbol this state is for |
| current_phase | TEXT | Current phase name |
| variables_json | TEXT | Runtime variables as JSON |
| bars_in_phase | INTEGER | Bars since entering current phase |
| phase_timeframe_bars_json | TEXT | Bar count per timeframe in phase |
| fired_once_rules_json | TEXT | Names of once-only rules already fired |
| open_ticket | INTEGER | MT5 ticket of open position (null if none) |
| open_direction | TEXT | BUY or SELL (null if no position) |
| updated_at | TIMESTAMP | Auto-set |

UNIQUE constraint on `(playbook_id, symbol)`.

#### `trade_journal`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| trade_id | INTEGER FK | References trades.id |
| signal_id | INTEGER FK | References signals.id |
| strategy_id | INTEGER FK | References strategies.id |
| playbook_db_id | INTEGER FK | References playbooks.id |
| symbol | TEXT | Trading symbol |
| direction | TEXT | BUY or SELL |
| lot_initial | REAL | Original lot size |
| lot_remaining | REAL | After partial closes |
| open_price | REAL | Entry price |
| close_price | REAL | Exit price |
| sl_initial | REAL | Initial stop loss |
| tp_initial | REAL | Initial take profit |
| sl_final | REAL | Final SL after modifications |
| tp_final | REAL | Final TP after modifications |
| open_time | TIMESTAMP | Entry time |
| close_time | TIMESTAMP | Exit time |
| duration_seconds | INTEGER | Trade duration |
| bars_held | INTEGER | Bars held (reserved) |
| pnl | REAL | Profit/loss |
| pnl_pips | REAL | P&L in pips |
| rr_achieved | REAL | Risk/reward ratio achieved |
| outcome | TEXT | `win`, `loss`, `breakeven` |
| exit_reason | TEXT | Why the trade was closed |
| playbook_phase_at_entry | TEXT | Phase when trade was opened |
| variables_at_entry_json | TEXT | Playbook variables at entry |
| entry_snapshot_json | TEXT | All indicator values at entry |
| exit_snapshot_json | TEXT | All indicator values at exit |
| entry_conditions_json | TEXT | Conditions that triggered entry |
| exit_conditions_json | TEXT | Conditions that triggered exit |
| market_context_json | TEXT | ATR, session, trend, spread at entry |
| management_events_json | TEXT | Array of SL/TP/trailing/partial close events |
| created_at | TIMESTAMP | Auto-set |

#### `build_sessions`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| playbook_id | INTEGER FK | References playbooks.id |
| natural_language | TEXT | Input NL description |
| skills_used | TEXT | JSON array of indicator skill names loaded |
| model_used | TEXT | Claude model ID used |
| prompt_tokens | INTEGER | Input tokens consumed |
| completion_tokens | INTEGER | Output tokens consumed |
| duration_ms | INTEGER | Build duration in milliseconds |
| created_at | TIMESTAMP | Auto-set |

#### `settings`
| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PK | Setting key (e.g., `user:admin`, risk limits) |
| value_json | TEXT | JSON-encoded value |

#### `indicator_log`
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| symbol | TEXT | Trading symbol |
| timeframe | TEXT | Timeframe |
| indicator | TEXT | Indicator name |
| values_json | TEXT | Indicator values as JSON |
| bar_time | TIMESTAMP | Bar timestamp |

#### `_migration_flags`
| Column | Type | Description |
|--------|------|-------------|
| flag | TEXT PK | Migration identifier |

### Relationships

```
strategies --< signals (strategy_id)
strategies --< trades (strategy_id)
signals --< trades (signal_id)
playbooks --< signals (playbook_db_id)
playbooks --< trades (playbook_db_id)
playbooks --< playbook_state (playbook_id)
playbooks --< trade_journal (playbook_db_id)
playbooks --< build_sessions (playbook_id)
trades --< trade_journal (trade_id)
signals --< trade_journal (signal_id)
```

### Indexes

- `idx_signals_strategy` on signals(strategy_id)
- `idx_signals_status` on signals(status)
- `idx_signals_created` on signals(created_at)
- `idx_trades_strategy` on trades(strategy_id)
- `idx_trades_symbol` on trades(symbol)
- `idx_playbook_state_playbook` on playbook_state(playbook_id)
- `idx_journal_trade` on trade_journal(trade_id)
- `idx_journal_playbook` on trade_journal(playbook_db_id)
- `idx_journal_symbol` on trade_journal(symbol)
- `idx_journal_outcome` on trade_journal(outcome)
- `idx_journal_open_time` on trade_journal(open_time)
- `idx_build_sessions_playbook` on build_sessions(playbook_id)

---

## Dashboard Architecture

React single-page application built with Vite, TypeScript, and Tailwind CSS.

### Pages

| Page | Component | Purpose |
|------|-----------|---------|
| `/` | `Dashboard.tsx` | Overview: account info, live ticker, active strategies/playbooks, recent signals |
| `/login` | `Login.tsx` | JWT authentication (register/login) |
| `/strategies` | `Strategies.tsx` | List all strategies, create from NL, toggle enable/disable |
| `/strategies/:id` | `StrategyEditor.tsx` | Edit strategy config, AI chat sidebar, indicator panel |
| `/playbooks` | `Playbooks.tsx` | List playbooks, build from NL, toggle enable/disable |
| `/playbooks/:id` | `PlaybookEditor.tsx` | Runtime state, phase flow, indicators, config editor, AI refinement chat |
| `/signals` | `Signals.tsx` | Signal history with filtering |
| `/trades` | `Trades.tsx` | Trade history and open positions |
| `/journal` | `Journal.tsx` | Trade journal with filters, expandable rows, analytics summary |
| `/analytics` | `Analytics.tsx` | Per-strategy performance metrics and breakdown |
| `/settings` | `Settings.tsx` | Risk limits, kill switch, global settings |

### Key Components

| Component | Purpose |
|-----------|---------|
| `LiveTicker.tsx` | Real-time bid/ask display from WebSocket |
| `KillSwitch.tsx` | Emergency kill switch button |
| `SignalCard.tsx` | Individual signal display with status badge |
| `StrategyCard.tsx` | Strategy summary card with enable/disable toggle |
| `StrategyChat.tsx` | Multi-turn AI chat about strategy refinement |
| `PlaybookCard.tsx` | Playbook summary card with phase pills and autonomy badge |
| `PlaybookChat.tsx` | AI refinement chat using trade journal data |
| `IndicatorPanel.tsx` | Live indicator values display |

### State Management

Zustand stores in `dashboard/src/store/`:

| Store | File | State |
|-------|------|-------|
| Auth | `auth.ts` | JWT token, user info, login/logout actions |
| Market | `market.ts` | Live ticks, account info, indicator values |
| Signals | `signals.ts` | Signal list, filter state |
| Strategies | `strategies.ts` | Strategy list, CRUD actions |
| Playbooks | `playbooks.ts` | Playbook list, build/toggle/delete actions |

### API Client (`dashboard/src/api/client.ts`)

- `fetch`-based HTTP client with JWT auth header injection
- Base URL: `/api` (relative, proxied in dev via Vite)
- Auto-attaches `Authorization: Bearer <token>` header
- Auto-clears token and redirects on 401 responses

### WebSocket Client (`dashboard/src/api/ws.ts`)

- Auto-reconnect WebSocket to `ws://localhost:8000/api/ws`
- Receives events: `tick`, `signal`, `trade`, `account`
- Updates Zustand stores on message receipt

---

## Configuration (`agent/config.py`)

Pydantic Settings with `.env` file support.

| Setting | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | `""` | Claude API key |
| `MT5_ZMQ_HOST` | `127.0.0.1` | ZMQ connection host |
| `MT5_ZMQ_REP_PORT` | `5555` | REQ/REP port |
| `MT5_ZMQ_PUB_PORT` | `5556` | PUB/SUB port |
| `API_HOST` | `0.0.0.0` | FastAPI bind host |
| `API_PORT` | `8000` | FastAPI bind port |
| `JWT_SECRET` | `change-this-...` | JWT signing secret |
| `JWT_EXPIRY_HOURS` | `168` | Token expiry (7 days) |
| `TELEGRAM_BOT_TOKEN` | `""` | Telegram notifications (optional) |
| `TELEGRAM_CHAT_ID` | `""` | Telegram chat ID (optional) |
| `DB_PATH` | `data/trade_agent.db` | SQLite database path |
| `PLAYBOOKS_DIR` | `data/playbooks` | Playbook storage directory |
| `DEFAULT_MAX_LOT` | `0.1` | Default max lot size |
| `DEFAULT_MAX_DAILY_TRADES` | `10` | Default max daily trades |
| `DEFAULT_MAX_DRAWDOWN_PCT` | `5.0` | Default max drawdown % |
| `DEFAULT_MAX_OPEN_POSITIONS` | `5` | Default max open positions |

---

## File Structure

```
trade-agent/
  agent/
    __init__.py
    main.py                 # Entry point (uvicorn runner)
    config.py               # Pydantic settings
    bridge.py               # ZMQ Bridge to MT5
    data_manager.py         # Market data buffers
    strategy_engine.py      # Legacy rule-based strategies
    playbook_engine.py      # Phase state machine runner
    playbook_eval.py        # Expression evaluator
    trade_executor.py       # Signal routing + execution
    risk_manager.py         # Risk checks
    journal_writer.py       # Trade journal capture
    ai_service.py           # Claude API integration
    notifications.py        # Telegram notifications
    api/
      __init__.py
      main.py               # FastAPI app factory + lifespan
      auth.py               # JWT auth (register/login)
      strategies.py         # Strategy CRUD routes
      playbooks.py          # Playbook CRUD + build/refine routes
      signals.py            # Signal routes
      trades.py             # Trade routes
      market.py             # Market data routes
      settings_routes.py    # Settings + risk limit routes
      journal.py            # Journal + analytics routes
      ws.py                 # WebSocket endpoint + broadcast
    db/
      __init__.py
      database.py           # SQLite async database layer
      migrations/
        001_initial.sql
        002_playbook_and_journal.sql
    models/
      __init__.py
      market.py             # Tick, Bar, IndicatorValue, MarketSnapshot
      strategy.py           # Strategy, StrategyConfig, ConditionGroup, Rule
      playbook.py           # Playbook, PlaybookConfig, Phase, Transition
      signal.py             # Signal, SignalDirection, SignalStatus
      trade.py              # Trade, Position, AccountInfo
      journal.py            # TradeJournalEntry, MarketContext, ManagementEvent
    indicators/
      catalog.json          # Indicator definitions
      skills/               # Per-indicator skill files (.md)
        _combinations.md
        RSI.md
        EMA.md
        ...
    prompts/
      strategy_parser.md
      signal_reasoner.md
      strategy_chat.md
      playbook_builder.md
      playbook_refiner.md
  mt5/
    TradeAgent.mq5          # MT5 Expert Advisor
  dashboard/
    src/
      main.tsx              # React entry point
      App.tsx               # Router + layout
      api/
        client.ts           # fetch-based HTTP client
        ws.ts               # WebSocket client (auto-reconnect)
      store/
        auth.ts             # Auth state (Zustand)
        market.ts           # Market state
        signals.ts          # Signals state
        strategies.ts       # Strategies state
        playbooks.ts        # Playbooks state
      pages/
        Dashboard.tsx
        Login.tsx
        Strategies.tsx
        StrategyEditor.tsx
        Playbooks.tsx
        PlaybookEditor.tsx
        Signals.tsx
        Trades.tsx
        Journal.tsx
        Analytics.tsx
        Settings.tsx
      components/
        LiveTicker.tsx
        KillSwitch.tsx
        SignalCard.tsx
        StrategyCard.tsx
        StrategyChat.tsx
        PlaybookCard.tsx
        PlaybookChat.tsx
        IndicatorPanel.tsx
      lib/
        utils.ts
  data/                     # Runtime data (gitignored)
    trade_agent.db
    trade_agent.log
  scripts/
    test_full_flow.py       # Integration test
  vercel.json               # Vercel deployment config (Vite dashboard)
  .env                      # Environment variables
  requirements.txt          # Python dependencies
```
