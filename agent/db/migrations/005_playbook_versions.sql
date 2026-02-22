-- Playbook version history for rollback support

CREATE TABLE IF NOT EXISTS playbook_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',  -- 'build', 'manual', 'refine', 'refine_backtest'
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (playbook_id) REFERENCES playbooks(id),
    UNIQUE(playbook_id, version)
);

CREATE INDEX IF NOT EXISTS idx_pb_versions_playbook ON playbook_versions(playbook_id, version DESC);
