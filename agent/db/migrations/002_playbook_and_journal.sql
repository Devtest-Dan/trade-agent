-- Playbook and Journal schema

CREATE TABLE IF NOT EXISTS playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description_nl TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',
    autonomy TEXT NOT NULL DEFAULT 'signal_only',
    enabled INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playbook_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    current_phase TEXT NOT NULL DEFAULT 'idle',
    variables_json TEXT NOT NULL DEFAULT '{}',
    bars_in_phase INTEGER NOT NULL DEFAULT 0,
    phase_timeframe_bars_json TEXT NOT NULL DEFAULT '{}',
    fired_once_rules_json TEXT NOT NULL DEFAULT '[]',
    open_ticket INTEGER,
    open_direction TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (playbook_id) REFERENCES playbooks(id),
    UNIQUE(playbook_id, symbol)
);

CREATE TABLE IF NOT EXISTS trade_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    signal_id INTEGER,
    strategy_id INTEGER,
    playbook_db_id INTEGER,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    lot_initial REAL NOT NULL,
    lot_remaining REAL,
    open_price REAL NOT NULL,
    close_price REAL,
    sl_initial REAL,
    tp_initial REAL,
    sl_final REAL,
    tp_final REAL,
    open_time TIMESTAMP,
    close_time TIMESTAMP,
    duration_seconds INTEGER,
    bars_held INTEGER,
    pnl REAL,
    pnl_pips REAL,
    rr_achieved REAL,
    outcome TEXT,
    exit_reason TEXT,
    playbook_phase_at_entry TEXT,
    variables_at_entry_json TEXT NOT NULL DEFAULT '{}',
    entry_snapshot_json TEXT NOT NULL DEFAULT '{}',
    exit_snapshot_json TEXT NOT NULL DEFAULT '{}',
    entry_conditions_json TEXT NOT NULL DEFAULT '{}',
    exit_conditions_json TEXT NOT NULL DEFAULT '{}',
    market_context_json TEXT NOT NULL DEFAULT '{}',
    management_events_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES trades(id),
    FOREIGN KEY (signal_id) REFERENCES signals(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id),
    FOREIGN KEY (playbook_db_id) REFERENCES playbooks(id)
);

CREATE TABLE IF NOT EXISTS build_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_id INTEGER,
    natural_language TEXT NOT NULL,
    skills_used TEXT NOT NULL DEFAULT '[]',
    model_used TEXT NOT NULL DEFAULT '',
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (playbook_id) REFERENCES playbooks(id)
);

-- Add playbook references to existing tables
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we use a safe approach
CREATE TABLE IF NOT EXISTS _migration_flags (flag TEXT PRIMARY KEY);

-- Add playbook_db_id to trades if not already added
INSERT OR IGNORE INTO _migration_flags (flag) VALUES ('002_trades_playbook_col');
-- We'll handle the ALTER TABLE in Python code since SQLite PRAGMA table_info check is needed

-- Add playbook_db_id to signals if not already added
INSERT OR IGNORE INTO _migration_flags (flag) VALUES ('002_signals_playbook_col');

-- Indexes
CREATE INDEX IF NOT EXISTS idx_playbook_state_playbook ON playbook_state(playbook_id);
CREATE INDEX IF NOT EXISTS idx_journal_trade ON trade_journal(trade_id);
CREATE INDEX IF NOT EXISTS idx_journal_playbook ON trade_journal(playbook_db_id);
CREATE INDEX IF NOT EXISTS idx_journal_symbol ON trade_journal(symbol);
CREATE INDEX IF NOT EXISTS idx_journal_outcome ON trade_journal(outcome);
CREATE INDEX IF NOT EXISTS idx_journal_open_time ON trade_journal(open_time);
CREATE INDEX IF NOT EXISTS idx_build_sessions_playbook ON build_sessions(playbook_id);
