"""GET /api/v1/audit-events: the admin audit log view (#71)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from src.audit import AuditAction, record_audit_event
from src.models import (
    AuditEvent,
    ClientProfile,
    ClientProfileVersion,
    DocumentKind,
    OnboardingJob,
    Role,
)

URL = "/api/v1/audit-events"


@pytest.fixture
def admin(sign_in):
    return sign_in(Role.ADMIN)


def _event(db_session, actor, action, object_type, object_id, version_id=None, at=None):
    event = record_audit_event(
        db_session,
        actor_id=actor.id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        version_id=version_id,
    )
    if at is not None:
        event.created_at = at
    db_session.commit()
    return event


def test_signed_out_is_401(client, monkeypatch):
    from src.auth import current_user
    from src.main import app

    monkeypatch.delitem(app.dependency_overrides, current_user, raising=False)
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_non_admins_are_403(sign_in, role):
    signed_in, _ = sign_in(role)
    assert signed_in.get(URL).status_code == 403


def test_empty_log(admin):
    signed_in, _ = admin
    response = signed_in.get(URL)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


def test_events_have_readable_details(admin, db_session, stored_document, demo_client):
    signed_in, user = admin
    document = stored_document(filename="call-notes.txt")
    intake = stored_document(filename="intake.txt")
    document.kind = DocumentKind.TRANSCRIPT
    intake.kind = DocumentKind.INTAKE
    job = OnboardingJob(
        client_id=demo_client.id,
        transcript_document_id=document.id,
        intake_document_id=intake.id,
    )
    profile = ClientProfile(client_id=demo_client.id)
    db_session.add_all([job, profile])
    db_session.flush()
    version = ClientProfileVersion(
        client_profile_id=profile.id, version_number=3, data={"x": 1}
    )
    db_session.add(version)
    db_session.commit()

    start = datetime.now(timezone.utc) - timedelta(minutes=5)
    _event(
        db_session, user, AuditAction.UPLOAD, "source_document", document.id, at=start
    )
    _event(
        db_session,
        user,
        AuditAction.JOB_STARTED,
        "onboarding_job",
        job.id,
        at=start + timedelta(minutes=1),
    )
    _event(
        db_session,
        user,
        AuditAction.APPROVE,
        "client_profile",
        profile.id,
        version.id,
        at=start + timedelta(minutes=2),
    )

    items = signed_in.get(URL).json()["items"]

    assert [item["action"] for item in items] == ["approve", "job_started", "upload"]
    approve, job_started, upload = items
    for item in items:
        assert item["actor_id"] == str(user.id)
        assert item["actor_name"] == user.display_name
        assert item["actor_email"] == user.email
        assert item["client_id"] == str(demo_client.id)
        assert item["client_name"] == demo_client.name
    assert approve["object_type"] == "client_profile"
    assert approve["object_id"] == str(profile.id)
    assert approve["version_id"] == str(version.id)
    assert approve["version_number"] == 3
    assert approve["document_filename"] is None
    assert job_started["object_id"] == str(job.id)
    assert job_started["version_number"] is None
    assert upload["document_filename"] == "call-notes.txt"


def test_missing_object_leaves_details_empty(admin, db_session):
    signed_in, user = admin
    _event(
        db_session, user, AuditAction.EDIT, "client_profile", uuid.uuid4(), uuid.uuid4()
    )

    (item,) = signed_in.get(URL).json()["items"]

    assert item["action"] == "edit"
    assert item["actor_name"] == user.display_name
    assert item["client_id"] is None
    assert item["client_name"] is None
    assert item["version_number"] is None


def test_pages_cover_every_event_once_newest_first(admin, db_session):
    signed_in, user = admin
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    # Two events share each timestamp, as events saved in one transaction do.
    expected = []
    for minute in range(5):
        for _ in range(2):
            event = _event(
                db_session,
                user,
                AuditAction.UPLOAD,
                "source_document",
                uuid.uuid4(),
                at=start + timedelta(minutes=minute),
            )
            expected.append((event.created_at, event.id))
    expected.sort(reverse=True)

    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        body = signed_in.get(URL, params=params).json()
        pages += 1
        seen.extend(uuid.UUID(item["id"]) for item in body["items"])
        # An event recorded mid-read is newer than every cursor, so it never
        # shifts later pages.
        if pages == 1:
            _event(
                db_session, user, AuditAction.UPLOAD, "source_document", uuid.uuid4()
            )
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == [event_id for _, event_id in expected]
    assert pages == 4


def test_last_full_page_has_no_next_cursor(admin, db_session):
    signed_in, user = admin
    for _ in range(2):
        _event(db_session, user, AuditAction.UPLOAD, "source_document", uuid.uuid4())

    body = signed_in.get(URL, params={"limit": 2}).json()

    assert len(body["items"]) == 2
    assert body["next_cursor"] is None


@pytest.mark.parametrize("limit", [0, 101])
def test_limit_is_bounded(admin, limit):
    signed_in, _ = admin
    assert signed_in.get(URL, params={"limit": limit}).status_code == 422


@pytest.mark.parametrize("cursor", ["not-base64!", "bm8tc2VwYXJhdG9y", "Zm9vfGJhcg=="])
def test_malformed_cursor_is_400(admin, cursor):
    signed_in, _ = admin
    response = signed_in.get(URL, params={"cursor": cursor})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid cursor"


def test_reading_the_log_records_nothing(admin, db_session):
    signed_in, _ = admin
    signed_in.get(URL)
    assert db_session.query(AuditEvent).count() == 0


def test_created_at_index_exists(db_session):
    names = (
        db_session.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'audit_events'")
        )
        .scalars()
        .all()
    )
    assert "ix_audit_events_created_at_id" in names
