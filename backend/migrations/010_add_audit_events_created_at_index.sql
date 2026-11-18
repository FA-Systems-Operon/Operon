-- Apply after 008_add_audit_events.sql. Lets the audit log view (#71) read newest first.
CREATE INDEX IF NOT EXISTS ix_audit_events_created_at_id ON audit_events (created_at, id);
