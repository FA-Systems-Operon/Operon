-- Apply after the users table exists (M10).
ALTER TABLE onboarding_jobs
    ADD COLUMN IF NOT EXISTS initiated_by UUID REFERENCES users(id);
