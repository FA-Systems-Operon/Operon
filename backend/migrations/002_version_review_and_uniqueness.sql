-- Upgrade existing #18/#19 version tables for the #20/#21 models.
-- Stop the API while applying. Run with psql -v ON_ERROR_STOP=1.
-- Fresh databases use SQLAlchemy create_all instead.
BEGIN;
LOCK TABLE client_profile_versions, playbook_versions IN ACCESS EXCLUSIVE MODE;
DO $$
DECLARE
    table_name text;
    parent_column text;
    constraint_name text;
    has_duplicates boolean;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['client_profile_versions', 'playbook_versions']
    LOOP
        parent_column := CASE table_name
            WHEN 'client_profile_versions' THEN 'client_profile_id'
            ELSE 'playbook_id' END;
        constraint_name := table_name || '_' || parent_column || '_version_number_key';
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %I GROUP BY %I, version_number HAVING count(*) > 1)',
            table_name, parent_column
        ) INTO has_duplicates;
        IF has_duplicates THEN
            RAISE EXCEPTION 'Duplicate version numbers in %; resolve explicitly before rerunning. No rows were removed.', table_name;
        END IF;

        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS approved_by UUID', table_name);
        IF NOT EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass(table_name) AND attname = 'status'
              AND NOT attisdropped
        ) THEN
            EXECUTE format('ALTER TABLE %I ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT ''draft''', table_name);
            -- Only a recorded approval timestamp establishes past approval.
            -- The historical approver is unknown; leave approved_by NULL.
            EXECUTE format('UPDATE %I SET status = ''approved'' WHERE approved_at IS NOT NULL', table_name);
            EXECUTE format('ALTER TABLE %I ALTER COLUMN status DROP DEFAULT', table_name);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = to_regclass(table_name) AND conname = constraint_name
        ) THEN
            EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I UNIQUE (%I, version_number)',
                           table_name, constraint_name, parent_column);
        END IF;
        EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (status)',
                       'ix_' || table_name || '_status', table_name);
    END LOOP;
END $$;
COMMIT;
