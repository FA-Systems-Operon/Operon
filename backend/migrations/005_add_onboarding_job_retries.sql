-- Add retry and lease columns to onboarding_jobs for task #37.
-- Safe to rerun. Apply after 004. Fresh databases use SQLAlchemy create_all.
BEGIN;
ALTER TABLE onboarding_jobs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE onboarding_jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE onboarding_jobs ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
COMMIT;
