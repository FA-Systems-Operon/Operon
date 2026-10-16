-- For databases that already have the #18 version tables. Fresh databases
-- receive these columns through SQLAlchemy create_all at application startup.
-- Existing snapshots remain unapproved; no approval is inferred from history.
BEGIN;
ALTER TABLE client_profile_versions
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE playbook_versions
    ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
COMMIT;
