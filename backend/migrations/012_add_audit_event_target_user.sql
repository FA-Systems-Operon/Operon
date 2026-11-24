-- Existing workflow events have no target user.
ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS target_user_id UUID REFERENCES users(id);
