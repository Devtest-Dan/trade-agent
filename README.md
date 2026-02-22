# Trade Agent

AI-powered multi-timeframe trading agent that connects to MetaTrader 5 via ZeroMQ. Strategies are described in natural language, compiled into deterministic playbooks by Claude, and executed locally with zero AI calls at runtime.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Stack](#stack)
- [Key Features](#key-features)
- [Directory Structure](#directory-structure)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [MT5 Expert Advisor](#mt5-expert-advisor)
  - [Environment Variables](#environment-variables)
  - [Running](#running)
- [Execution Systems](#execution-systems)
  - [Strategy Engine (Legacy)](#strategy-engine-legacy)
  - [Playbook Engine](#playbook-engine)
- [Playbook Lifecycle](#playbook-lifecycle)
- [Expression Language](#expression-language)
- [Database](#database)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [Health](#health)
  - [Strategies](#strategies)
  - [Playbooks](#playbooks)
  - [Journal](#journal)
  - [Signals](#signals)
  - [Trades](#trades)
  - [Market](#market)
  - [Settings](#settings)
  - [Backtest](#backtest)
  - [Knowledge Graph](#knowledge-graph)
  - [Data Import](#data-import)
  - [WebSocket](#websocket)
- [Indicators](#indicators)
- [Dashboard](#dashboard)

---

## Overview

Trade Agent has two execution systems:

1. **Strategy Engine** (legacy) -- flat 4-condition groups (`entry_long`, `exit_long`, `entry_short`, `exit_short`) evaluated on bar close.
2. **Playbook Engine** (new) -- multi-phase state machines with dynamic expressions, position management, and full trade journaling.

The AI (Claude) is only used at **build time** to create playbooks from natural language. At runtime, playbooks execute as deterministic state machines with zero AI calls.

---

## Architecture

```
BUILD TIME (AI)                          RUNTIME (Local Brain)
+----------------------+                +------------------------------+
| User NL description  |                | PlaybookEngine               |
| + Indicator Skills   |---> Playbook ->|  +- Phase state machine      |
| + Catalog + Schema   |    (JSON)      |  +- Expression evaluator     |
| + Claude Opus        |                |  +- Position management      |
+----------------------+                |  +- Journal writer           |
                                        |     (no AI calls)            |
REFINE TIME (AI)                        +------------------------------+
+----------------------+                              |
| Trade Journal data   |                              v
| + Playbook config    |<----------------- Trade Journal (SQLite)
| + Skills files       |                 full snapshots + outcomes
| + Claude Sonnet      |
+----------------------+
```

- **Build time:** Claude Opus reads the user's natural language strategy description, indicator skills files, the indicator catalog, and the playbook JSON schema. It produces a complete playbook configuration (JSON).
- **Runtime:** The PlaybookEngine evaluates phase transitions on each bar close, fires actions (set variables, open/close trades), runs position management rules (breakeven, trailing stop, partial close), and writes full context to the trade journal. No AI calls are made.
- **Refine time:** Claude Sonnet ingests trade journal data, the current playbook config, and indicator skills files to suggest targeted improvements.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ (FastAPI, asyncio, aiosqlite, ZeroMQ, Anthropic SDK) |
| MT5 EA | MQL5 Expert Advisor (ZMQ REP:5555, PUB:5556) |
| Dashboard | React + Vite + TypeScript + Tailwind CSS |
| Database | SQLite with WAL mode |
| AI (build time) | Claude Opus for playbook building, Claude Sonnet for refinement |

---

## Key Features

- **13 indicators** -- RSI, EMA, SMA, MACD, Stochastic, Bollinger, ATR, ADX, CCI, WilliamsR, SMC\_Structure, OB\_FVG, NW\_Envelope
- **3 autonomy levels** -- `signal_only`, `semi_auto`, `full_auto`
- **Multi-phase playbook state machines** with transitions, timeouts, and variables
- **Safe expression evaluator** -- AST-based, no `eval()`
- **Position management** -- breakeven, trailing stop, partial close, dynamic SL/TP
- **Full trade journal** with indicator snapshots, market context, and management event log
- **Per-condition win rate analytics**
- **AI-assisted playbook refinement** using journal data
- **15 indicator skills files** giving Claude deep trading knowledge
- **Telegram notifications** -- signals, trade opens, position management events
- **Real-time WebSocket updates** -- tick, signal, and trade events
- **Kill switch** for emergency position closure
- **JWT authentication**
- **Skill Graphs** -- auto-extracts trading insights from backtests into a knowledge graph (nodes + edges), injects into AI prompts during playbook build/refine
- **Interactive knowledge visualization** -- force-directed graph on the `/knowledge` page (react-force-graph-2d)
- **Historical backtesting** -- run playbooks against imported .hst data with full metrics and trade replay
- **Data import** -- import MT4 .hst files and CSV bars for backtesting
- **Trade Control** -- desktop service manager with system tray, auto-start on boot, health monitoring, auto-restart
- **Circuit breaker** -- auto-disables playbooks after consecutive losses or errors

---

## Directory Structure

```
trade-agent/
├── agent/                      # Python backend
│   ├── main.py                 # Entry point (uvicorn)
│   ├── config.py               # Pydantic settings (.env)
│   ├── ai_service.py           # Claude API (build + refine playbooks)
│   ├── bridge.py               # ZeroMQ MT5 bridge
│   ├── data_manager.py         # OHLCV + indicator buffers
│   ├── strategy_engine.py      # Legacy condition evaluator
│   ├── playbook_engine.py      # State machine runner
│   ├── playbook_eval.py        # Safe expression evaluator (AST)
│   ├── journal_writer.py       # Trade context capture
│   ├── trade_executor.py       # Signal routing + MT5 orders
│   ├── risk_manager.py         # Risk gates + kill switch
│   ├── notifications.py        # Telegram notifier
│   ├── models/
│   │   ├── market.py           # Tick, Bar, IndicatorValue, MarketSnapshot
│   │   ├── signal.py           # Signal, SignalDirection, SignalStatus
│   │   ├── strategy.py         # Strategy, StrategyConfig, Condition, Rule
│   │   ├── trade.py            # Trade, Position, AccountInfo
│   │   ├── playbook.py         # PlaybookConfig, Phase, Transition, etc.
│   │   └── journal.py          # TradeJournalEntry, MarketContext
│   ├── db/
│   │   ├── database.py         # Async SQLite layer
│   │   └── migrations/
│   │       ├── 001_initial.sql
│   │       └── 002_playbook_and_journal.sql
│   ├── api/
│   │   ├── main.py             # FastAPI app factory + lifespan
│   │   ├── auth.py             # JWT + bcrypt
│   │   ├── strategies.py       # Strategy CRUD + AI parse
│   │   ├── playbooks.py        # Playbook build/manage/refine
│   │   ├── journal.py          # Journal entries + analytics
│   │   ├── signals.py          # Signal list + approve/reject
│   │   ├── trades.py           # Trade history
│   │   ├── market.py           # Live data
│   │   ├── settings_routes.py  # Risk settings
│   │   └── ws.py               # WebSocket broadcast
│   ├── indicators/
│   │   ├── catalog.json        # 13 indicators (10 standard + 3 custom SMC)
│   │   └── skills/             # 15 indicator reference files for AI
│   │       ├── _template.md
│   │       ├── _combinations.md
│   │       ├── RSI.md, EMA.md, SMA.md, MACD.md, Stochastic.md
│   │       ├── Bollinger.md, ATR.md, ADX.md, CCI.md, WilliamsR.md
│   │       └── SMC_Structure.md, OB_FVG.md, NW_Envelope.md
│   ├── indicator_processor.py  # AI indicator analysis
│   ├── knowledge_extractor.py  # Skill extraction from backtests
│   ├── backtest/
│   │   ├── engine.py           # Backtest engine (bar-by-bar replay)
│   │   └── import_manager.py   # .hst and CSV import
│   ├── models/
│   │   ├── ...existing...
│   │   ├── knowledge.py        # SkillNode, SkillEdge, enums
│   │   └── backtest.py         # BacktestConfig, BacktestResult
│   ├── api/
│   │   ├── ...existing...
│   │   ├── knowledge.py        # Skill graph CRUD + extraction
│   │   ├── backtest.py         # Backtest runner + results
│   │   ├── charting.py         # Chart data endpoints
│   │   ├── data_import.py      # .hst/.csv import endpoints
│   │   └── indicators.py       # Indicator catalog
│   ├── db/
│   │   └── migrations/
│   │       ├── 001_initial.sql
│   │       ├── 002_playbook_and_journal.sql
│   │       ├── ...
│   │       └── 009_skill_graphs.sql
│   └── prompts/
│       ├── strategy_parser.md
│       ├── signal_reasoner.md
│       ├── strategy_chat.md
│       ├── playbook_builder.md
│       └── playbook_refiner.md
├── dashboard/                   # React frontend
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts       # REST API client (fetch-based)
│   │   │   └── ws.ts           # WebSocket client (auto-reconnect)
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx, Login.tsx
│   │   │   ├── Strategies.tsx, StrategyEditor.tsx
│   │   │   ├── Playbooks.tsx, PlaybookEditor.tsx
│   │   │   ├── Signals.tsx, Trades.tsx, Journal.tsx
│   │   │   ├── Analytics.tsx, Settings.tsx
│   │   ├── components/
│   │   │   ├── StrategyCard.tsx, StrategyChat.tsx
│   │   │   ├── PlaybookCard.tsx, PlaybookChat.tsx
│   │   │   ├── SignalCard.tsx, IndicatorPanel.tsx
│   │   │   ├── KillSwitch.tsx, LiveTicker.tsx
│   │   └── store/
│   │       ├── auth.ts, market.ts, signals.ts
│   │       ├── strategies.ts, playbooks.ts
│   └── dist/                   # Built output
├── mt5/
│   └── TradeAgent.mq5          # MT5 Expert Advisor
├── data/
│   ├── trade_agent.db          # SQLite database
│   └── trade_agent.log         # Rotating log
├── scripts/
│   ├── install_mt5_ea.py
│   ├── test_custom_indicators.py
│   └── test_full_flow.py
├── TradeControl/               # Desktop service manager
│   ├── trade_control.py        # Main app (tkinter + pystray)
│   ├── trade_control.pyw       # Windowless launcher
│   ├── setup.bat               # One-time setup + auto-start
│   └── trade_icon.ico          # System tray icon
├── vercel.json                 # Vercel deployment config (Vite dashboard)
├── .env                        # Environment variables
└── requirements.txt
```

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- MetaTrader 5 terminal
- An Anthropic API key (for playbook building)

### Installation

```bash
git clone https://github.com/Devtest-Dan/trade-agent.git
cd trade-agent
pip install -r requirements.txt
```

Copy the example environment file and fill in your keys:

```bash
cp .env.example .env
```

### MT5 Expert Advisor

1. Copy `mt5/TradeAgent.mq5` to your MT5 `Experts` folder (typically `MQL5/Experts/`).
2. Compile the EA in MetaEditor.
3. Attach the compiled EA to a chart in MT5.
4. Ensure the EA is enabled and ZeroMQ ports are accessible.

Alternatively, run the install script:

```bash
python scripts/install_mt5_ea.py
```

### Environment Variables

Create a `.env` file in the project root with the following:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET=your-secret-here

# MT5 ZeroMQ connection
MT5_ZMQ_HOST=127.0.0.1
MT5_ZMQ_REP_PORT=5555
MT5_ZMQ_PUB_PORT=5556

# API server
API_HOST=0.0.0.0
API_PORT=8000

# JWT
JWT_EXPIRY_HOURS=168

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Database
DB_PATH=data/trade_agent.db

# Risk defaults
DEFAULT_MAX_LOT=0.1
DEFAULT_MAX_DAILY_TRADES=10
DEFAULT_MAX_DRAWDOWN_PCT=5.0
DEFAULT_MAX_OPEN_POSITIONS=5
```

### Running

**Start the backend:**

```bash
python -m agent.main
```

The API server starts on `http://localhost:8000`.

**Start the dashboard:**

```bash
cd dashboard
npm install
npm run dev
```

The dashboard opens at `http://localhost:5173`. Register an account to begin.

---

## Execution Systems

### Strategy Engine (Legacy)

The original execution system. Strategies are defined as flat 4-condition groups:

- `entry_long` -- conditions to open a long position
- `exit_long` -- conditions to close a long position
- `entry_short` -- conditions to open a short position
- `exit_short` -- conditions to close a short position

Conditions are evaluated on each bar close. When all conditions in a group are satisfied, the corresponding signal is generated. Claude parses natural language into these condition groups via the strategy parser prompt.

### Playbook Engine

The new execution system. Playbooks are multi-phase state machines that support:

- **Phases** -- named states (e.g., `scanning`, `entry_ready`, `in_trade`, `managing`)
- **Transitions** -- conditional edges between phases with trigger expressions
- **Actions** -- operations fired on transition (set variables, open/close trades)
- **Variables** -- dynamic values scoped to the playbook instance
- **Position management** -- breakeven, trailing stop, partial close, dynamic SL/TP
- **Timeouts** -- phase-level time limits that force transitions
- **Trade journaling** -- full context capture on every trade event

Playbooks are built by Claude Opus from natural language and stored as JSON in the database. At runtime, the PlaybookEngine evaluates them deterministically with no AI calls.

---

## Playbook Lifecycle

1. **Describe** -- The user describes a strategy in natural language.
2. **Build** -- Claude Opus reads the description along with indicator skills files, the indicator catalog, and the playbook JSON schema. It produces a complete playbook configuration.
3. **Review** -- The playbook is saved to the database. The user reviews phases, transitions, and parameters in the dashboard.
4. **Enable** -- The user enables the playbook. The PlaybookEngine begins evaluating it on each bar close.
5. **Execute** -- Transitions fire actions: set variables, open trades, close trades. Position management rules run: breakeven, trailing stop, partial close.
6. **Journal** -- The JournalWriter captures full context on every trade: indicator snapshots, market context, phase at entry/exit, management events.
7. **Refine** -- The user triggers a refinement session. Claude Sonnet ingests journal analytics and the current playbook config, then suggests targeted improvements.

---

## Expression Language

The playbook expression system uses AST parsing (no `eval()`) for safe runtime evaluation. Supported syntax:

| Token | Description | Example |
|-------|-------------|---------|
| `ind.<id>.<field>` | Indicator value | `ind.h4_atr.value` |
| `prev.<id>.<field>` | Previous bar's indicator value | `prev.h4_rsi.value` |
| `var.<name>` | Playbook variable | `var.entry_price` |
| `_price` | Current mid price | `_price` |
| `trade.<field>` | Open trade field | `trade.open_price` |
| `risk.<field>` | Risk config field | `risk.max_lot` |

**Operators:**

- Comparison: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Arithmetic: `+`, `-`, `*`, `/` with parentheses
- Logical: `and`, `or`, `not`

**Example expressions:**

```
ind.h4_rsi.value < 30 and ind.d1_ema.value > _price
trade.open_price + ind.h4_atr.value * 1.5
var.swing_high - var.swing_low > ind.h4_atr.value * 2
```

---

## Database

SQLite with WAL mode. Migrations auto-run on startup.

**Tables:**

| Table | Purpose |
|-------|---------|
| `strategies` | Legacy strategy configurations |
| `signals` | Generated signals (pending, approved, rejected) |
| `trades` | Trade history and outcomes |
| `settings` | Risk and system settings |
| `playbooks` | Playbook configurations (JSON) |
| `playbook_state` | Current phase and variable state per playbook |
| `trade_journal` | Full trade context snapshots and outcomes |
| `build_sessions` | AI build/refine session history |
| `indicator_log` | Indicator computation log |
| `backtest_runs` | Backtest session configs and results |
| `backtest_trades` | Individual backtest trades |
| `skill_nodes` | Knowledge graph skill nodes |
| `skill_edges` | Knowledge graph edges between nodes |
| `imported_bars` | Imported historical bar data |

Migration files are located in `agent/db/migrations/`.

---

## API Reference

All endpoints require a JWT token in the `Authorization: Bearer <token>` header unless noted otherwise.

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register a new account |
| POST | `/api/auth/login` | Login and receive a JWT |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health check (no auth required) |

### Strategies

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/strategies` | List all strategies |
| POST | `/api/strategies` | Create strategy (AI parses natural language) |
| GET | `/api/strategies/:id` | Get strategy by ID |
| PUT | `/api/strategies/:id` | Update strategy |
| DELETE | `/api/strategies/:id` | Delete strategy |
| PUT | `/api/strategies/:id/toggle` | Enable/disable strategy |
| PUT | `/api/strategies/:id/autonomy` | Set autonomy level |
| POST | `/api/strategies/:id/chat` | Chat with AI about strategy |

### Playbooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/playbooks` | Build a new playbook from natural language |
| GET | `/api/playbooks` | List all playbooks |
| GET | `/api/playbooks/:id` | Get playbook by ID |
| PUT | `/api/playbooks/:id` | Update playbook |
| DELETE | `/api/playbooks/:id` | Delete playbook |
| PUT | `/api/playbooks/:id/toggle` | Enable/disable playbook |
| POST | `/api/playbooks/:id/refine` | AI-assisted refinement using journal data |
| GET | `/api/playbooks/:id/state` | Get current playbook runtime state |

### Journal

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/journal` | List journal entries |
| GET | `/api/journal/:id` | Get journal entry by ID |
| GET | `/api/journal/analytics` | Aggregate journal analytics |
| GET | `/api/journal/analytics/conditions` | Per-condition win rate analytics |

### Signals

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/signals` | List all signals |
| POST | `/api/signals/:id/approve` | Approve a pending signal |
| POST | `/api/signals/:id/reject` | Reject a pending signal |

### Trades

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/trades` | Trade history |
| GET | `/api/trades/open` | Currently open trades |

### Market

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/:symbol` | Live market data for a symbol |
| GET | `/api/market/account` | MT5 account info |
| GET | `/api/market/indicators` | Current indicator values |

### Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Get current risk/system settings |
| PUT | `/api/settings` | Update settings |
| POST | `/api/kill-switch` | Activate kill switch (close all positions) |
| POST | `/api/kill-switch/deactivate` | Deactivate kill switch |

### Backtest

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/backtest/run` | Run a backtest on imported data |
| GET | `/api/backtest/runs` | List backtest runs |
| GET | `/api/backtest/runs/:id` | Get backtest result |

### Knowledge Graph

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/knowledge/skills` | List/search skill nodes |
| POST | `/api/knowledge/skills` | Create manual skill node |
| GET | `/api/knowledge/skills/:id` | Get skill with edges |
| PUT | `/api/knowledge/skills/:id` | Update skill node |
| DELETE | `/api/knowledge/skills/:id` | Delete skill node |
| GET | `/api/knowledge/skills/:id/graph` | BFS graph traversal |
| POST | `/api/knowledge/extract/:backtest_id` | Extract skills from backtest |
| DELETE | `/api/knowledge/extract/:backtest_id` | Delete extracted skills |
| POST | `/api/knowledge/edges` | Create edge |
| DELETE | `/api/knowledge/edges/:id` | Delete edge |
| GET | `/api/knowledge/graph` | Full graph for visualization |
| GET | `/api/knowledge/stats` | Summary stats |

### Data Import

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/data/import/hst` | Import MT4 .hst file |
| POST | `/api/data/import/csv` | Import CSV bars |
| GET | `/api/data/import/symbols` | List imported symbols |

### WebSocket

```
ws://localhost:8000/api/ws?token=<JWT>
```

Real-time events pushed over WebSocket:

- **tick** -- new price tick
- **signal** -- new signal generated
- **trade** -- trade opened/closed/modified
- **state** -- playbook state change

---

## Indicators

13 indicators are available, defined in `agent/indicators/catalog.json`:

**Standard (10):**

| Indicator | Description |
|-----------|-------------|
| RSI | Relative Strength Index |
| EMA | Exponential Moving Average |
| SMA | Simple Moving Average |
| MACD | Moving Average Convergence Divergence |
| Stochastic | Stochastic Oscillator |
| Bollinger | Bollinger Bands |
| ATR | Average True Range |
| ADX | Average Directional Index |
| CCI | Commodity Channel Index |
| WilliamsR | Williams %R |

**Custom SMC (3):**

| Indicator | Description |
|-----------|-------------|
| SMC\_Structure | Smart Money Concept market structure |
| OB\_FVG | Order Blocks and Fair Value Gaps |
| NW\_Envelope | Nadaraya-Watson Envelope |

Each indicator has a corresponding skills file in `agent/indicators/skills/` that provides Claude with deep knowledge about the indicator's behavior, common parameters, signal interpretation, and effective combinations.

---

## Dashboard

The React dashboard provides a full interface for managing strategies, playbooks, signals, and trades.

**Pages:**

- **Dashboard** -- Overview with live ticker, account summary, active strategies/playbooks, recent signals
- **Strategies** -- Create, edit, toggle, and chat about legacy strategies
- **Strategy Editor** -- JSON config editor with AI chat sidebar
- **Playbooks** -- Build, review, enable, and manage playbook state machines
- **Playbook Editor** -- Runtime state visualization, phase flow, indicators, JSON config, AI refinement chat
- **Signals** -- View pending signals, approve or reject in `signal_only` / `semi_auto` mode
- **Trades** -- Trade history and currently open positions
- **Journal** -- Trade journal entries with filters, expandable rows, analytics summary
- **Analytics** -- Per-strategy performance metrics and breakdown
- **Settings** -- Risk parameters, kill switch
- **Backtest** -- Run backtests, view results, extract skills
- **Knowledge** -- Interactive force-directed graph visualization, skill list with filters

**Key components:**

- `IndicatorPanel` -- live indicator values display
- `KillSwitch` -- emergency position closure button
- `LiveTicker` -- real-time price feed
- `StrategyCard` -- strategy summary with enable/disable toggle
- `StrategyChat` -- multi-turn AI chat for strategy refinement
- `PlaybookCard` -- playbook summary with phase pills
- `PlaybookChat` -- AI refinement chat using journal data
- `SignalCard` -- individual signal display with status badge
- `SkillGraph` -- force-directed knowledge graph (react-force-graph-2d)

**State management (Zustand):**

- `auth.ts` -- JWT token, login/logout
- `market.ts` -- live ticks, account info
- `signals.ts` -- signal list, filters
- `strategies.ts` -- strategy list, CRUD
- `playbooks.ts` -- playbook list, build, toggle

The dashboard connects to the backend via REST API and WebSocket for real-time updates.

---

## License

This project is proprietary. All rights reserved.
