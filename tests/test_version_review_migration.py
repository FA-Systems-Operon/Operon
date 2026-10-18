"""Verify upgrades preserve history and reject ambiguous duplicates atomically."""

import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from src.db import engine

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "backend/migrations/002_version_review_and_uniqueness.sql"
).read_text()
TABLES = ("client_profile_versions", "playbook_versions")


@pytest.fixture
def legacy_database(database):
    # A separate schema keeps migration DDL out of the ORM fixture's tables.
    schema = "migration_" + uuid.uuid4().hex
    url = engine.url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
        )
        try:
            for table, parent in zip(
                TABLES, ("client_profile_id", "playbook_id"), strict=True
            ):
                connection.execute(
                    sql.SQL("""
                    CREATE TABLE {} (
                        id INTEGER PRIMARY KEY, {} INTEGER NOT NULL,
                        version_number INTEGER NOT NULL, data JSONB NOT NULL,
                        approved_at TIMESTAMPTZ
                    )
                """).format(sql.Identifier(table), sql.Identifier(parent))
                )
                connection.execute(
                    sql.SQL("""
                    INSERT INTO {} VALUES
                    (1, 10, 1, '{{"history": "approved"}}', '2026-01-01T00:00:00Z'),
                    (2, 10, 2, '{{"history": "draft"}}', NULL)
                """).format(sql.Identifier(table))
                )
            yield connection
        finally:
            connection.execute("ROLLBACK")
            connection.execute("SET search_path TO public")
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def test_upgrade_preserves_approval_and_is_repeatable(legacy_database):
    connection = legacy_database
    connection.execute(MIGRATION)
    for table in TABLES:
        rows = connection.execute(
            sql.SQL(
                "SELECT data, status, approved_at, approved_by FROM {} ORDER BY id"
            ).format(sql.Identifier(table))
        ).fetchall()
        assert rows[0][0] == {"history": "approved"}
        assert rows[0][1] == "approved"
        assert rows[0][2].isoformat() == "2026-01-01T00:00:00+00:00"
        assert rows[0][3] is None
        assert rows[1] == ({"history": "draft"}, "draft", None, None)
        connection.execute(
            sql.SQL("UPDATE {} SET status = 'in_review' WHERE id = 2").format(
                sql.Identifier(table)
            )
        )
    connection.execute(MIGRATION)
    for table in TABLES:
        assert (
            connection.execute(
                sql.SQL("SELECT status FROM {} WHERE id = 2").format(
                    sql.Identifier(table)
                )
            ).fetchone()[0]
            == "in_review"
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            connection.execute(
                sql.SQL(
                    "INSERT INTO {} SELECT 3, 10, 1, data, approved_at, approved_by, status FROM {} WHERE id = 1"
                ).format(sql.Identifier(table), sql.Identifier(table))
            )


@pytest.mark.parametrize("duplicate_table", TABLES)
def test_duplicate_history_aborts_upgrade_without_deleting_rows(
    legacy_database, duplicate_table
):
    connection = legacy_database
    connection.execute(
        sql.SQL(
            "INSERT INTO {} SELECT 3, 10, 1, data, approved_at FROM {} WHERE id = 1"
        ).format(sql.Identifier(duplicate_table), sql.Identifier(duplicate_table))
    )
    with pytest.raises(
        psycopg.errors.RaiseException, match="Duplicate version numbers"
    ):
        connection.execute(MIGRATION)
    connection.execute("ROLLBACK")
    for table in TABLES:
        # Even if the first table was upgraded before the second failed, all
        # schema changes must roll back with the transaction.
        assert (
            connection.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s AND column_name = 'status'",
                (table,),
            ).fetchone()[0]
            == 0
        )
    assert (
        connection.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(duplicate_table))
        ).fetchone()[0]
        == 3
    )
