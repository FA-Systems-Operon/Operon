-- Add source_documents.kind (transcript or intake) for task #35.
-- Safe to rerun. Existing documents keep kind = NULL; their data is unchanged.
-- Fresh databases use SQLAlchemy create_all instead.
BEGIN;
ALTER TABLE source_documents ADD COLUMN IF NOT EXISTS kind VARCHAR(20);
COMMIT;
