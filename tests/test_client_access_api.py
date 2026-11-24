"""Admin client grants through real sign-in and CSRF checks."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import func, select

from src.auth import current_user
from src.main import app
from src.models import ClientAccess, Role


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
