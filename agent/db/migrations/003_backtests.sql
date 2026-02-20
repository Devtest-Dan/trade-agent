-- Phase 3: Backtesting tables

CREATE TABLE IF NOT EXISTS bar_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, timeframe, bar_time)
);

CREATE INDEX IF NOT EXISTS idx_bar_cache_lookup ON bar_cache(symbol, timeframe, bar_time);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_count INTEGER NOT NULL DEFAULT 500,
    status TEXT NOT NULL DEFAULT 'pending',
    config_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (playbook_id) REFERENCES playbooks(id)
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_playbook ON backtest_runs(playbook_id);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    direction TEXT NOT NULL,
    open_bar_idx INTEGER NOT NULL,
    close_bar_idx INTEGER NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL NOT NULL,
    open_time TEXT,
    close_time TEXT,
    sl REAL,
    tp REAL,
    lot REAL NOT NULL DEFAULT 0.1,
    pnl REAL NOT NULL DEFAULT 0,
    pnl_pips REAL NOT NULL DEFAULT 0,
    rr_achieved REAL,
    outcome TEXT,
    exit_reason TEXT,
    phase_at_entry TEXT,
    variables_at_entry_json TEXT DEFAULT '{}',
    entry_indicators_json TEXT DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_run ON backtest_trades(run_id);
