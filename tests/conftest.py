"""Shared test setup: a separate Postgres test database and temporary file storage.

Tests never touch the dev database (operon). They use TEST_DATABASE_URL, which
defaults to an operon_test database on the compose "db" service (see .env.example).
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, make_url, text

# Lets tests import the app as "src...", since the package lives in backend/src.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://operon:change-me@localhost:5432/operon_test",
)

# Safety check: refuse to run (and wipe tables) against a non-test database.
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError(
        f"TEST_DATABASE_URL must point to a *_test database: {TEST_DATABASE_URL}"
    )

# Must be set before importing src: src.config reads DATABASE_URL at import time,
# so this makes the app's own engine point at the test database. This applies to
# every test, including test_api.py and test_config.py.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
from fastapi.testclient import TestClient

from src.db import Base, SessionLocal, engine, get_db
from src.main import app
from src.models import Client
from src.storage import LocalFileStorage, get_storage


def _create_test_database() -> None:
    """Create the test database if it doesn't exist (compose only creates operon_dev)."""
    url = make_url(engine.url)
    # CREATE DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def database():
    """Create all tables once for the whole test run, and drop them at the end."""
    _create_test_database()
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(database):
    """A session shared by the test and the app, so both see the same data."""
    session = SessionLocal()
    yield session
    session.close()
    # Empty every table so each test starts from a clean database.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE extracted_texts, source_documents, clients"))


@pytest.fixture
def storage(tmp_path):
    """File storage in a fresh temporary folder for each test."""
    return LocalFileStorage(tmp_path)


@pytest.fixture
def client(db_session, storage):
    """HTTP client for the app, with the database and storage swapped for test ones."""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_storage] = lambda: storage
    # Not using "with TestClient(app)", so the app's startup create_all doesn't
    # run; the database fixture above already created the tables.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def demo_client(db_session):
    """A client row that documents can be uploaded for."""
    demo = Client(name="Demo Client")
    db_session.add(demo)
    db_session.commit()
    return demo
