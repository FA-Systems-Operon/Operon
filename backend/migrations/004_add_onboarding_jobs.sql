-- Add onboarding_jobs for task #36: one onboarding-agent run per transcript and
-- intake pair, started once both files are uploaded.
-- Safe to rerun. Fresh databases use SQLAlchemy create_all instead.
-- If you applied an earlier draft of this file (with a document_id column),
-- run DROP TABLE onboarding_jobs; first. It held no reviewed data.
BEGIN;
CREATE TABLE IF NOT EXISTS onboarding_jobs (
    id UUID PRIMARY KEY,
    client_id UUID NOT NULL REFERENCES clients (id),
    transcript_document_id UUID NOT NULL REFERENCES source_documents (id),
    intake_document_id UUID NOT NULL REFERENCES source_documents (id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error TEXT,
    result_version_id UUID REFERENCES client_profile_versions (id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE (transcript_document_id, intake_document_id)
);
CREATE INDEX IF NOT EXISTS ix_onboarding_jobs_client_id ON onboarding_jobs (client_id);
CREATE INDEX IF NOT EXISTS ix_onboarding_jobs_transcript_document_id
    ON onboarding_jobs (transcript_document_id);
CREATE INDEX IF NOT EXISTS ix_onboarding_jobs_intake_document_id
    ON onboarding_jobs (intake_document_id);
CREATE INDEX IF NOT EXISTS ix_onboarding_jobs_status ON onboarding_jobs (status);
COMMIT;
