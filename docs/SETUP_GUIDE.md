# Trade Agent Setup Guide

Step-by-step instructions to get the Trade Agent running on your machine.

---

## Prerequisites

- **Python 3.11+** -- required for `X | None` union syntax and `asyncio` improvements
- **Node.js 18+** -- for the React dashboard (Vite build tool)
- **MetaTrader 5 terminal** -- with an active broker account (demo or live)
- **Anthropic API key** -- for AI-powered strategy parsing and playbook building (optional for manual strategies)

---

## Step 1: Clone and Install Python Dependencies

```bash
git clone https://github.com/Devtest-Dan/trade-agent.git
cd trade-agent
pip install -r requirements.txt
```

Key Python packages:
- `fastapi` + `uvicorn` -- web framework and ASGI server
- `aiosqlite` -- async SQLite driver
- `zmq` (pyzmq) -- ZeroMQ bindings for MT5 communication
- `anthropic` -- Claude API client
- `pydantic` + `pydantic-settings` -- data models and configuration
- `loguru` -- structured logging
- `PyJWT` -- JSON Web Token authentication

---

## Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Required for AI features (strategy parsing, playbook building)
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Required for authentication security
JWT_SECRET=generate-a-random-string-at-least-32-chars

# Optional: MT5 ZMQ ports (defaults shown)
MT5_ZMQ_HOST=127.0.0.1
MT5_ZMQ_REP_PORT=5555
MT5_ZMQ_PUB_PORT=5556

# Optional: API server (defaults shown)
API_HOST=0.0.0.0
API_PORT=8000

# Optional: Database path (default shown)
DB_PATH=data/trade_agent.db

# Optional: Telegram notifications
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Optional: Risk defaults
DEFAULT_MAX_LOT=0.1
DEFAULT_MAX_DAILY_TRADES=10
DEFAULT_MAX_DRAWDOWN_PCT=5.0
DEFAULT_MAX_OPEN_POSITIONS=5
```

If you do not have an `.env.example` file, create `.env` manually with at least the `ANTHROPIC_API_KEY` and `JWT_SECRET` values.

---

## Step 3: Install MT5 Expert Advisor

### 3.1 Install ZeroMQ for MQL5

The EA uses the [mql-zmq](https://github.com/dingmaotu/mql-zmq) library by Ding Li.

1. Download the mql-zmq release from GitHub
2. Copy the following files to your MT5 installation:
   - `libzmq.dll` and `libsodium.dll` -> `MQL5/Libraries/`
   - `Zmq/` folder (containing `Zmq.mqh` and related headers) -> `MQL5/Include/`
3. Verify the DLLs are in the correct location:
   ```
   C:\Users\<YOU>\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL5\Libraries\libzmq.dll
   C:\Users\<YOU>\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL5\Include\Zmq\Zmq.mqh
   ```

### 3.2 Install the Expert Advisor

1. Open MetaTrader 5
2. Copy `mt5/TradeAgent.mq5` to your `MQL5/Experts/` folder:
   ```
   C:\Users\<YOU>\AppData\Roaming\MetaQuotes\Terminal\<ID>\MQL5\Experts\TradeAgent.mq5
   ```
3. Open MetaEditor (F4 from MT5)
4. Open `TradeAgent.mq5` and compile (F7)
5. Ensure compilation succeeds with 0 errors

### 3.3 Attach the EA to a Chart

1. In MT5, open any chart (e.g., XAUUSD H1)
2. Drag `TradeAgent` from the Navigator panel onto the chart
3. In the EA properties dialog:
   - **Common tab**: Check "Allow DLL imports" and "Allow algo trading"
   - **Inputs tab**: Verify port numbers (default: REP=5555, PUB=5556)
4. Click OK
5. Verify the EA is running: check the Experts tab for `[TradeAgent] Initialized successfully`
6. Enable "Algo Trading" button in the MT5 toolbar (green icon)

**Important:** The EA must be attached to a chart for ZeroMQ sockets to be active. The chart symbol does not matter -- the EA handles all symbols dynamically via the SUBSCRIBE command.

---

## Step 4: Start the Backend

```bash
python -m agent.main
```

Expected output:

```
12:00:00 | INFO     | agent.main:main - ============================================================
12:00:00 | INFO     | agent.main:main -   Trade Agent -- AI-Powered MT5 Trading System
12:00:00 | INFO     | agent.main:main - ============================================================
12:00:00 | INFO     | agent.main:main - API: http://0.0.0.0:8000
12:00:00 | INFO     | agent.main:main - MT5: tcp://127.0.0.1:5555 (REP) / tcp://127.0.0.1:5556 (PUB)
12:00:00 | INFO     | agent.db.database:connect - Database connected: data/trade_agent.db
12:00:00 | INFO     | agent.bridge:connect - ZMQ connected -- REQ: tcp://127.0.0.1:5555, SUB: tcp://127.0.0.1:5556
12:00:00 | INFO     | agent.api.main:lifespan - Trade Agent ready. MT5 connected: True
```

The API is available at **http://localhost:8000**.

**Offline mode:** If MT5 is not running, you will see:

```
12:00:00 | WARNING  | agent.api.main:lifespan - MT5 not connected: ... Running in offline mode.
12:00:00 | INFO     | agent.api.main:lifespan - Trade Agent ready. MT5 connected: False
```

In offline mode, the API still works for strategy management, playbook building, and dashboard access. Live market data and trade execution are unavailable.

**Logging:** Logs are written to both stderr and `data/trade_agent.log` (10 MB rotation, 7 days retention).

---

## Step 5: Start the Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Expected output:

```
  VITE v5.x.x  ready in XXX ms

  ->  Local:   http://localhost:5173/
  ->  Network: http://192.168.x.x:5173/
```

Open **http://localhost:5173** in your browser.

---

## Step 5b: (Optional) Install Trade Control

Trade Control is a desktop service manager that auto-starts the backend and dashboard on boot, with system tray, health monitoring, and auto-restart.

```bash
cd TradeControl
setup.bat
```

This will:
1. Install dependencies (psutil, pystray, Pillow, pywin32)
2. Generate the system tray icon
3. Create a Windows startup shortcut

After setup, Trade Control will launch automatically on boot. To start it manually:

```bash
cd TradeControl
python trade_control.pyw
```

**Features:**
- System tray icon (green/yellow/red based on service health)
- Auto-starts backend (port 8000) and dashboard (port 5173)
- Health monitoring every 10 seconds with auto-restart after 3 failures
- Port cleanup for stale processes
- MetaTrader 5 detection
- Quick-access buttons: Open Dashboard, API Docs, Project, Logs

---

## Step 6: Create an Account

### Via the Dashboard

1. Navigate to http://localhost:5173
2. You will be redirected to the login page
3. Click "Register" and create a username/password

### Via the API

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-secure-password"}'
```

Response:

```json
{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}
```

Save the `access_token` for subsequent API calls.

### Login (if account already exists)

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-secure-password"}'
```

---

## Step 7: Build Your First Playbook

Playbooks are the recommended way to define strategies. They are built from natural language and run as deterministic state machines.

### Via the API

```bash
curl -X POST http://localhost:8000/api/playbooks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "description": "Buy XAUUSD when H4 RSI is oversold below 30 and price bounces from Bollinger lower band on M15. Set stop loss 1.5x ATR below entry. Take profit at 2x risk. Trail stop loss to breakeven when 1R profit reached."
  }'
```

The AI service will:
1. Identify indicators mentioned (RSI, Bollinger, ATR)
2. Load relevant indicator skill files
3. Generate a `PlaybookConfig` with phases, transitions, and management rules
4. Return the full playbook configuration

Response includes:

```json
{
  "id": 1,
  "name": "H4 RSI Oversold Bollinger Bounce",
  "config": { ... },
  "build_session": {
    "skills_used": ["RSI", "Bollinger", "ATR"],
    "model_used": "claude-opus-4-20250514",
    "prompt_tokens": 3200,
    "completion_tokens": 1800,
    "duration_ms": 4500
  }
}
```

### Via the Dashboard

1. Navigate to the **Playbooks** page (sidebar)
2. Click "New Playbook"
3. Type your strategy description in natural language
4. Click "Build Playbook" -- Claude Opus will generate the playbook configuration
5. Review the generated phases, transitions, and rules
6. Enable the playbook to start receiving signals

---

## Step 8: Enable and Monitor

### Enable a Playbook

Via API:

```bash
curl -X PUT http://localhost:8000/api/playbooks/1/toggle \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Via Dashboard: Toggle the enable switch on the playbook card.

### Monitor

**Dashboard:** The main dashboard shows:
- Live ticker with current bid/ask prices
- Recent signals with status (pending/executed/rejected)
- Active positions with P&L
- Account equity and margin

**WebSocket events:** Connect to `ws://localhost:8000/api/ws` for real-time updates:
- `tick` -- price updates
- `signal` -- new signals from strategies/playbooks
- `trade` -- trade executions
- `account` -- account info updates

**Logs:** Check `data/trade_agent.log` for detailed component-level logging.

**Journal analytics:** Query the journal API for playbook performance:

```bash
curl http://localhost:8000/api/journal/analytics?playbook_db_id=1 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Returns win rate, average PnL, average R:R, exit reason breakdown, and more.

---

## Step 9: Refine Your Playbook (Optional)

After accumulating trade journal data, use the refinement endpoint to improve your playbook:

```bash
curl -X POST http://localhost:8000/api/playbooks/1/refine \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "messages": [
      {"role": "user", "content": "The strategy is getting stopped out too often during London session. Can you widen the SL for that session?"}
    ]
  }'
```

The AI will analyze your journal data (win rate, per-condition performance, recent trade samples) and suggest modifications. If it generates a config update, it will be included in the response.

---

## Troubleshooting

### Port 8000 already in use

Another process is using the port. Either kill it or change the port:

```bash
# Find the process
netstat -ano | findstr :8000

# Or change the port in .env
API_PORT=8001
```

### MT5 not connected

1. Ensure the TradeAgent EA is attached to a chart in MT5
2. Verify "Algo Trading" is enabled in MT5 toolbar
3. Check that "Allow DLL imports" is checked in EA properties
4. Confirm ZMQ DLLs (`libzmq.dll`) are in `MQL5/Libraries/`
5. Check the Experts tab in MT5 for error messages
6. Verify port numbers match between `.env` and EA inputs (default: 5555, 5556)

### "Invalid x-api-key" or AI features not working

Set the `ANTHROPIC_API_KEY` environment variable in your `.env` file:

```env
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-key-here
```

Restart the backend after changing `.env`.

### Database locked

SQLite allows only one writer at a time. Ensure only one instance of the backend is running:

```bash
# On Windows
tasklist | findstr python
```

Kill any duplicate processes.

### WebSocket connection drops

The dashboard WebSocket client auto-reconnects. If connections keep dropping:
- Check that the backend is running
- Verify CORS settings allow your dashboard origin
- Check browser console for errors

### Indicator "not ready" errors

When requesting a new indicator for the first time, MT5 needs time to calculate it. The Python bridge will log a warning:

```
Indicator RSI not ready. BarsCalculated=0
```

This is normal. The next tick cycle will retry and succeed once MT5 finishes calculation.

### ZMQ timeout errors

```
ZMQ timeout on command: GET_BARS
```

The EA did not respond within 5 seconds. Possible causes:
- MT5 is busy (e.g., downloading history data)
- EA was detached from the chart
- Network issue between Python and MT5 (unlikely on localhost)

The bridge auto-reconnects after a timeout.

---

## Running Tests

Run the integration test script:

```bash
python -m scripts.test_full_flow
```

This tests the full signal flow: strategy loading, indicator evaluation, signal generation, and trade execution.

---

## Health Check

Verify the system is running correctly:

```bash
curl http://localhost:8000/api/health
```

Response:

```json
{
  "status": "ok",
  "mt5_connected": true,
  "kill_switch": false
}
```

---

## Useful API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health check |
| `/api/auth/register` | POST | Create new user account |
| `/api/auth/login` | POST | Login and get JWT token |
| `/api/strategies` | GET | List all strategies |
| `/api/strategies` | POST | Create strategy from NL |
| `/api/playbooks` | GET | List all playbooks |
| `/api/playbooks` | POST | Build playbook from NL |
| `/api/playbooks/:id/refine` | POST | Refine playbook with AI |
| `/api/signals` | GET | List signals (filterable) |
| `/api/trades` | GET | List trades (filterable) |
| `/api/market/:symbol` | GET | Get current tick |
| `/api/account` | GET | Get account info |
| `/api/kill-switch` | POST | Activate kill switch |
| `/api/kill-switch/deactivate` | POST | Deactivate kill switch |
| `/api/journal` | GET | List journal entries (filterable) |
| `/api/journal/analytics` | GET | Journal performance analytics |
| `/api/journal/analytics/conditions` | GET | Per-condition win rates |
| `/api/playbooks/:id/state` | GET | Playbook runtime state |
| `/api/ws` | WebSocket | Real-time event stream |
| `/api/knowledge/skills` | GET | List skill graph nodes |
| `/api/knowledge/graph` | GET | Full knowledge graph for visualization |
| `/api/knowledge/stats` | GET | Knowledge graph statistics |
| `/api/knowledge/extract/:id` | POST | Extract skills from a backtest |
| `/api/backtest/run` | POST | Run a playbook backtest |
| `/api/backtest/runs` | GET | List backtest runs |
| `/api/data/import/hst` | POST | Import MT4 .hst file |

---

## Architecture Reference

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed component documentation, data flow diagrams, and database schema.
