"""Shared test setup: a separate Postgres test database and temporary file storage.

Tests never touch the dev database (operon). They use TEST_DATABASE_URL, which
defaults to an operon_test database on the compose "db" service (see .env.example).
"""

import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
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
    raise RuntimeError("TEST_DATABASE_URL must point to a *_test database")

# Must be set before importing src: src.config reads DATABASE_URL at import time,
# so this makes the app's own engine point at the test database. This applies to
# every test, including test_api.py and test_config.py.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
from fastapi.testclient import TestClient

from src.db import Base, SessionLocal, engine, get_db
from src.main import app
from src.models import (
    Client,
    ClientProfile,
    ClientProfileVersion,
    Playbook,
    PlaybookVersion,
    ReviewStatus,
    SourceDocument,
)
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
    Base.metadata.drop_all(engine)
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
        conn.execute(
            text(
                "TRUNCATE artifact_versions, artifacts, "
                "client_profile_versions, client_profiles, "
                "playbook_versions, playbooks, "
                "extracted_texts, source_documents, clients"
            )
        )


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
def client_factory(db_session):
    """Create independent synthetic clients in the isolated test database."""

    def create(name="Demo Client"):
        demo = Client(name=name)
        db_session.add(demo)
        db_session.commit()
        return demo

    return create


@pytest.fixture
def demo_client(client_factory):
    """A client row that documents can be uploaded for."""
    return client_factory()


@pytest.fixture
def stored_document(db_session, storage, demo_client):
    def create(
        data=b"Alice: Hello.  \r\n",
        filename="transcript.txt",
        content_type="application/octet-stream",
        *,
        owner=None,
    ):
        owner = demo_client if owner is None else owner
        document_id = uuid.uuid4()
        key = f"{owner.id}/{document_id}"
        storage.save(key, data)
        document = SourceDocument(
            id=document_id,
            client_id=owner.id,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            storage_key=key,
        )
        db_session.add(document)
        db_session.commit()
        return document

    return create


@pytest.fixture
def sample_profile():
    """Fresh illustrative profile data, not a production schema or persisted row."""
    return {
        "business_name": "Demo Client",
        "industry": "Consulting",
        "goals": ["Reduce manual onboarding"],
    }


def _approval_fields() -> dict:
    """Columns that make a version count as approved. Only for arranging test state;
    the code under test approves through the /approve endpoints."""
    return {
        "status": ReviewStatus.APPROVED,
        "approved_by": uuid.uuid4(),
        "approved_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def profile_factory(db_session, demo_client):
    """Create a ClientProfile with its version 1; returns that ClientProfileVersion.

    approved=True pre-approves v1 (skipping the endpoint), so tests can start from
    "a client with an approved profile" and exercise the later steps for real.
    """

    def create(owner=None, *, approved=False, data=None):
        owner = demo_client if owner is None else owner
        profile = ClientProfile(client_id=owner.id)
        db_session.add(profile)
        db_session.flush()
        version = ClientProfileVersion(
            client_profile_id=profile.id,
            version_number=1,
            data=data or {},
            **(_approval_fields() if approved else {}),
        )
        db_session.add(version)
        db_session.commit()
        return version

    return create


@pytest.fixture
def playbook_factory(db_session):
    """Create a Playbook with its version 1; returns that PlaybookVersion."""

    def create(*, approved=False, data=None):
        playbook = Playbook()
        db_session.add(playbook)
        db_session.flush()
        version = PlaybookVersion(
            playbook_id=playbook.id,
            version_number=1,
            data=data or {},
            **(_approval_fields() if approved else {}),
        )
        db_session.add(version)
        db_session.commit()
        return version

    return create


class OperonApi:
    """The HTTP calls the staleness tests act through. Every id argument may be a
    UUID, a str, or None, so ORM rows and JSON responses can be passed alike."""

    def __init__(self, http):
        self.http = http
        self.reviewer = str(uuid.uuid4())

    @staticmethod
    def _s(value):
        return None if value is None else str(value)

    def new_profile_version(self, profile_id, data=None):
        r = self.http.put(f"/client-profiles/{profile_id}", json=data or {"k": "v"})
        assert r.status_code == 200, r.text
        return r.json()

    def approve_profile(self, profile_id, version_id):
        return self.http.post(
            f"/client-profiles/{profile_id}/versions/{version_id}/approve",
            json={"approved_by": self.reviewer},
        )

    def new_playbook_version(self, playbook_id):
        r = self.http.put(f"/playbooks/{playbook_id}", json={"rule": "x"})
        assert r.status_code == 200, r.text
        return r.json()

    def approve_playbook(self, playbook_id, version_id):
        return self.http.post(
            f"/playbooks/{playbook_id}/versions/{version_id}/approve",
            json={"approved_by": self.reviewer},
        )

    def artifact(
        self,
        client_id,
        profile_version_id,
        playbook_version_id=None,
        kind="campaign_brief",
    ):
        return self.http.post(
            "/artifacts",
            json={
                "client_id": self._s(client_id),
                "kind": kind,
                "client_profile_version_id": self._s(profile_version_id),
                "playbook_version_id": self._s(playbook_version_id),
                "data": {"headline": "hello"},
            },
        )

    def new_artifact_version(
        self, artifact_id, profile_version_id, playbook_version_id=None
    ):
        return self.http.post(
            f"/artifacts/{artifact_id}/versions",
            json={
                "client_profile_version_id": self._s(profile_version_id),
                "playbook_version_id": self._s(playbook_version_id),
                "data": {"headline": "regenerated"},
            },
        )

    def approve_artifact(self, artifact_id, version_id):
        return self.http.post(
            f"/artifacts/{artifact_id}/versions/{version_id}/approve",
            json={"approved_by": self.reviewer},
        )

    def history(self, artifact_id) -> list[dict]:
        r = self.http.get(f"/artifacts/{artifact_id}/versions")
        assert r.status_code == 200, r.text
        return r.json()

    def stale(self, client_id=None) -> list[dict]:
        params = {"client_id": str(client_id)} if client_id else {}
        r = self.http.get("/artifacts/stale", params=params)
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def api(client):
    return OperonApi(client)
