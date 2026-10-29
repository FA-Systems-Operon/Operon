"""Verify the document-kind upgrade keeps existing documents and can be rerun."""

import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from src.db import engine

MIGRATION = (
    Path(__file__).resolve().parents[1] / "backend/migrations/003_add_document_kind.sql"
).read_text()


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
            connection.execute("""
                CREATE TABLE source_documents (
                    id INTEGER PRIMARY KEY, original_filename VARCHAR(255) NOT NULL
                )
            """)
            connection.execute(
                "INSERT INTO source_documents VALUES (1, 'old-transcript.txt')"
            )
            yield connection
        finally:
            connection.execute("SET search_path TO public")
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def test_upgrade_adds_nullable_kind_and_is_repeatable(legacy_database):
    connection = legacy_database

    connection.execute(MIGRATION)
    connection.execute("UPDATE source_documents SET kind = 'intake' WHERE id = 1")
    connection.execute(MIGRATION)

    assert connection.execute("SELECT * FROM source_documents").fetchall() == [
        (1, "old-transcript.txt", "intake")
    ]
    connection.execute(
        "INSERT INTO source_documents (id, original_filename) VALUES (2, 'x')"
    )
    assert connection.execute(
        "SELECT kind FROM source_documents WHERE id = 2"
    ).fetchone() == (None,)
