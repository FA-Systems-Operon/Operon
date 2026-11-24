"""Admin client grants through real sign-in and CSRF checks."""

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from src.audit import AuditAction
from src.auth import current_user
from src.main import app
from src.models import AuditEvent, Client, ClientAccess, Role


def grant_url(user_id, client_id):
    return f"/api/v1/users/{user_id}/clients/{client_id}"


@pytest.mark.parametrize("target_role", [Role.ADMIN, Role.REVIEWER, Role.VIEWER])
def test_admin_can_grant_client_access(sign_in, db_session, demo_client, target_role):
    admin_http, _ = sign_in(Role.ADMIN)
    _, target = sign_in(target_role)

    response = admin_http.put(grant_url(target.id, demo_client.id))

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"user_id", "client_id", "created_at"}
    assert body["user_id"] == str(target.id)
    assert body["client_id"] == str(demo_client.id)
    stored = db_session.get(ClientAccess, (target.id, demo_client.id))
    assert stored is not None
    assert stored.created_at == datetime.fromisoformat(body["created_at"])


def test_repeated_grant_preserves_assignment(sign_in, db_session, demo_client):
    admin_http, _ = sign_in(Role.ADMIN)
    _, target = sign_in(Role.REVIEWER)
    url = grant_url(target.id, demo_client.id)

    first = admin_http.put(url)
    second = admin_http.put(url)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert db_session.scalar(select(func.count()).select_from(ClientAccess)) == 1


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_grant_is_admin_only(sign_in, db_session, demo_client, role):
    http, user = sign_in(role)

    assert http.put(grant_url(user.id, demo_client.id)).status_code == 403
    assert db_session.scalar(select(func.count()).select_from(ClientAccess)) == 0


def test_grant_requires_sign_in(client, signed_in_user, demo_client):
    app.dependency_overrides.pop(current_user, None)

    assert client.put(grant_url(signed_in_user.id, demo_client.id)).status_code == 401


def test_grant_requires_csrf(sign_in, db_session, demo_client):
    http, admin = sign_in(Role.ADMIN)
    del http.headers["X-CSRF-Token"]

    assert http.put(grant_url(admin.id, demo_client.id)).status_code == 403
    assert db_session.scalar(select(func.count()).select_from(ClientAccess)) == 0


@pytest.mark.parametrize("missing", ["user", "client"])
def test_grant_missing_record_returns_404(sign_in, db_session, demo_client, missing):
    http, admin = sign_in(Role.ADMIN)
    user_id = uuid.uuid4() if missing == "user" else admin.id
    client_id = uuid.uuid4() if missing == "client" else demo_client.id

    assert http.put(grant_url(user_id, client_id)).status_code == 404
    assert db_session.scalar(select(func.count()).select_from(ClientAccess)) == 0


def test_revoke_removes_only_requested_assignment(sign_in, db_session, demo_client):
    http, admin = sign_in(Role.ADMIN)
    _, target = sign_in(Role.REVIEWER)
    other_client = Client(name="Other client")
    db_session.add(other_client)
    db_session.flush()
    pairs = [
        (target.id, demo_client.id),
        (target.id, other_client.id),
        (admin.id, demo_client.id),
    ]
    db_session.add_all(
        ClientAccess(user_id=user_id, client_id=client_id)
        for user_id, client_id in pairs
    )
    db_session.commit()

    response = http.delete(grant_url(target.id, demo_client.id))

    assert response.status_code == 204, response.text
    assert response.content == b""
    remaining = db_session.scalars(select(ClientAccess)).all()
    assert {(item.user_id, item.client_id) for item in remaining} == set(pairs[1:])


def test_repeated_revoke_and_regrant(sign_in, db_session, demo_client):
    http, target = sign_in(Role.ADMIN)
    url = grant_url(target.id, demo_client.id)
    assert http.put(url).status_code == 200

    assert http.delete(url).status_code == 204
    assert http.delete(url).status_code == 204
    assert db_session.get(ClientAccess, (target.id, demo_client.id)) is None
    assert http.put(url).status_code == 200
    assert db_session.get(ClientAccess, (target.id, demo_client.id)) is not None


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_revoke_is_admin_only(sign_in, db_session, demo_client, role):
    http, user = sign_in(role)
    db_session.add(ClientAccess(user_id=user.id, client_id=demo_client.id))
    db_session.commit()

    assert http.delete(grant_url(user.id, demo_client.id)).status_code == 403
    assert db_session.get(ClientAccess, (user.id, demo_client.id)) is not None


def test_revoke_requires_sign_in(client, signed_in_user, demo_client):
    app.dependency_overrides.pop(current_user, None)

    assert (
        client.delete(grant_url(signed_in_user.id, demo_client.id)).status_code == 401
    )


def test_revoke_requires_csrf(sign_in, db_session, demo_client):
    http, admin = sign_in(Role.ADMIN)
    db_session.add(ClientAccess(user_id=admin.id, client_id=demo_client.id))
    db_session.commit()
    del http.headers["X-CSRF-Token"]

    assert http.delete(grant_url(admin.id, demo_client.id)).status_code == 403
    assert db_session.get(ClientAccess, (admin.id, demo_client.id)) is not None


@pytest.mark.parametrize("missing", ["user", "client"])
def test_revoke_missing_record_returns_404(sign_in, demo_client, missing):
    http, admin = sign_in(Role.ADMIN)
    user_id = uuid.uuid4() if missing == "user" else admin.id
    client_id = uuid.uuid4() if missing == "client" else demo_client.id

    assert http.delete(grant_url(user_id, client_id)).status_code == 404


def test_revoke_commit_failure_preserves_assignment(
    sign_in, db_session, demo_client, monkeypatch
):
    http, admin = sign_in(Role.ADMIN)
    url = grant_url(admin.id, demo_client.id)
    assert http.put(url).status_code == 200

    def fail_commit():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="Simulated database failure"):
        http.delete(url)

    assert db_session.get(ClientAccess, (admin.id, demo_client.id)) is not None


def test_access_changes_record_admin_client_and_target_user(
    sign_in, db_session, demo_client
):
    http, admin = sign_in(Role.ADMIN)
    _, target = sign_in(Role.REVIEWER)
    url = grant_url(target.id, demo_client.id)

    assert http.put(url).status_code == 200
    assert http.put(url).status_code == 200
    assert http.delete(url).status_code == 204
    assert http.delete(url).status_code == 204

    events = db_session.scalars(select(AuditEvent)).all()
    assert len(events) == 2
    assert {event.action for event in events} == {
        AuditAction.CLIENT_ACCESS_GRANTED,
        AuditAction.CLIENT_ACCESS_REVOKED,
    }
    history = http.get("/api/v1/audit-events")
    assert history.status_code == 200
    visible = {item["id"]: item for item in history.json()["items"]}
    for event in events:
        assert event.actor_id == admin.id
        assert event.target_user_id == target.id
        assert event.object_type == "client"
        assert event.object_id == demo_client.id
        assert event.version_id is None
        assert event.created_at.tzinfo is not None
        item = visible[str(event.id)]
        assert item["target_user_id"] == str(target.id)
        assert item["client_id"] == str(demo_client.id)
        assert item["client_name"] == demo_client.name


@pytest.mark.parametrize("method", ["put", "delete"])
def test_failed_access_change_rolls_back_audit_event(
    sign_in, db_session, demo_client, monkeypatch, method
):
    http, admin = sign_in(Role.ADMIN)
    url = grant_url(admin.id, demo_client.id)
    if method == "delete":
        assert http.put(url).status_code == 200
    before = db_session.scalar(select(func.count()).select_from(AuditEvent))

    def fail_commit():
        db_session.flush()
        raise RuntimeError("Simulated commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="Simulated commit failure"):
        getattr(http, method)(url)

    assert db_session.scalar(select(func.count()).select_from(AuditEvent)) == before
    stored = db_session.get(ClientAccess, (admin.id, demo_client.id))
    assert (stored is not None) == (method == "delete")


def test_target_user_migration_can_be_reapplied(db_session, sign_in):
    _, admin = sign_in(Role.ADMIN)
    event = AuditEvent(
        actor_id=admin.id, action="edit", object_type="user", object_id=admin.id
    )
    db_session.add(event)
    db_session.commit()
    event_id = event.id
    migration = (
        Path(__file__).resolve().parents[1]
        / "backend/migrations/012_add_audit_event_target_user.sql"
    ).read_text()
    db_session.execute(text("ALTER TABLE audit_events DROP COLUMN target_user_id"))
    db_session.execute(text(migration))
    db_session.execute(text(migration))
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(AuditEvent, event_id)
    assert stored.target_user_id is None
    assert stored.actor_id == admin.id
