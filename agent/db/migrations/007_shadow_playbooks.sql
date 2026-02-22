-- Shadow playbook support: run refined playbooks in parallel before promoting
-- Columns added via _add_column_if_missing in database.py (ALTER TABLE not idempotent in SQLite)

CREATE INDEX IF NOT EXISTS idx_playbooks_shadow ON playbooks(shadow_of);
