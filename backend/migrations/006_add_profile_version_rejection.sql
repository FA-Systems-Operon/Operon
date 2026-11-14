-- Store why and when a reviewer rejected a client profile draft (#63).
-- Safe to rerun. Apply after 005. Fresh databases use SQLAlchemy create_all.
BEGIN;
ALTER TABLE client_profile_versions ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE client_profile_versions ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;
COMMIT;
