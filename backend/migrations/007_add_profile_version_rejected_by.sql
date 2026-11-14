-- Record which signed-in user rejected a client profile draft (#62).
-- Safe to rerun. Apply after 006. Fresh databases use SQLAlchemy create_all.
BEGIN;
ALTER TABLE client_profile_versions ADD COLUMN IF NOT EXISTS rejected_by UUID;
COMMIT;
