-- Refinement history: tracks every refine session with before/after context

CREATE TABLE IF NOT EXISTS refinement_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'journal',  -- 'journal', 'backtest'
    backtest_id INTEGER,  -- set when source='backtest'
    messages_json TEXT NOT NULL DEFAULT '[]',  -- conversation messages
    reply TEXT NOT NULL DEFAULT '',
    config_changed INTEGER NOT NULL DEFAULT 0,  -- 1 if config was updated
    before_version INTEGER,  -- playbook_versions.version before change
    after_version INTEGER,   -- playbook_versions.version after change
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (playbook_id) REFERENCES playbooks(id)
);

CREATE INDEX IF NOT EXISTS idx_refine_hist_playbook ON refinement_history(playbook_id, created_at DESC);
