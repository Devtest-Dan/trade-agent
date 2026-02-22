-- Skill Graphs: atomic trading insights extracted from backtests

CREATE TABLE IF NOT EXISTS skill_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'entry_pattern',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT 'LOW',
    source_type TEXT NOT NULL DEFAULT 'backtest',
    source_id INTEGER,
    playbook_id INTEGER,
    symbol TEXT,
    timeframe TEXT,
    market_regime TEXT,
    sample_size INTEGER NOT NULL DEFAULT 0,
    win_rate REAL NOT NULL DEFAULT 0.0,
    avg_pnl REAL NOT NULL DEFAULT 0.0,
    avg_rr REAL NOT NULL DEFAULT 0.0,
    indicators_json TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (playbook_id) REFERENCES playbooks(id)
);

CREATE INDEX IF NOT EXISTS idx_skill_nodes_category ON skill_nodes(category);
CREATE INDEX IF NOT EXISTS idx_skill_nodes_symbol ON skill_nodes(symbol);
CREATE INDEX IF NOT EXISTS idx_skill_nodes_playbook ON skill_nodes(playbook_id);
CREATE INDEX IF NOT EXISTS idx_skill_nodes_source ON skill_nodes(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_skill_nodes_confidence ON skill_nodes(confidence);
CREATE INDEX IF NOT EXISTS idx_skill_nodes_regime ON skill_nodes(market_regime);

CREATE TABLE IF NOT EXISTS skill_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relationship TEXT NOT NULL DEFAULT 'supports',
    weight REAL NOT NULL DEFAULT 1.0,
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES skill_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES skill_nodes(id) ON DELETE CASCADE,
    UNIQUE(source_id, target_id, relationship)
);

CREATE INDEX IF NOT EXISTS idx_skill_edges_source ON skill_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_skill_edges_target ON skill_edges(target_id);
