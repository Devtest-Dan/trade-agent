-- Shadow playbook support: run refined playbooks in parallel before promoting

ALTER TABLE playbooks ADD COLUMN shadow_of INTEGER REFERENCES playbooks(id);
ALTER TABLE playbooks ADD COLUMN is_shadow INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_playbooks_shadow ON playbooks(shadow_of);
