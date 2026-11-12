"""Invite by link: POST /api/v1/users/invite (admin only) and POST /api/v1/auth/accept-invite (public)."""

from fastapi.testclient import TestClient

from src import auth
from src.main import app
from src.models import Role

PASSWORD = "a-long-password-123"


def sign_in(client, db_session, email, role):
    """Create a user, log in, and return the CSRF header a browser would send."""
    auth.create_user(db_session, email, "Test User", PASSWORD, role)
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200
    return {auth.CSRF_HEADER: client.cookies.get(auth.CSRF_COOKIE)}


def invite(client, headers, email="nina@example.com", **extra):
    return client.post(
        "/api/v1/users/invite", json={"email": email, **extra}, headers=headers
    )


def accept(client, token, name="Nina", password=PASSWORD):
    return client.post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "display_name": name, "password": password},
    )


# --- inviting --------------------------------------------------------------


def test_a_generic_invite_gets_the_default_role(client, db_session):
    headers = sign_in(client, db_session, "admin@example.com", Role.ADMIN)

    response = invite(client, headers, "Nina@Example.com")  # no role sent

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "nina@example.com"
    assert body["role"] == "viewer"
    assert body["invite_token"]


def test_an_admin_can_still_choose_a_role_through_the_api(client, db_session):
    headers = sign_in(client, db_session, "admin@example.com", Role.ADMIN)
    assert invite(client, headers, role="reviewer").json()["role"] == "reviewer"


def test_invite_requires_sign_in(client):
    assert invite(client, {}).status_code == 401


def test_invite_is_admin_only(client, db_session):
    headers = sign_in(client, db_session, "rev@example.com", Role.REVIEWER)
    assert invite(client, headers).status_code == 403


def test_invite_needs_the_csrf_header(client, db_session):
    sign_in(client, db_session, "admin@example.com", Role.ADMIN)
    assert invite(client, {}).status_code == 403


def test_cannot_invite_an_email_that_already_has_an_account(client, db_session):
    headers = sign_in(client, db_session, "admin@example.com", Role.ADMIN)
    auth.create_user(db_session, "taken@example.com", "Taken", PASSWORD, Role.VIEWER)
    assert invite(client, headers, "taken@example.com").status_code == 409


def test_invite_rejects_a_bad_email(client, db_session):
    headers = sign_in(client, db_session, "admin@example.com", Role.ADMIN)
    assert invite(client, headers, "not-an-email").status_code == 422


# --- accepting -------------------------------------------------------------


def test_invite_then_accept_then_login(client, db_session):
    headers = sign_in(client, db_session, "admin@example.com", Role.ADMIN)
    token = invite(client, headers).json()["invite_token"]

    browser = TestClient(app)  # a different browser: no cookies from the admin
    accepted = accept(browser, token)

    assert accepted.status_code == 201
    assert accepted.json()["email"] == "nina@example.com"
    assert accepted.json()["role"] == "viewer"
    assert "password" not in accepted.text
    # Accepting only creates the account. The frontend signs in right afterwards.
    assert "set-cookie" not in accepted.headers
    login = browser.post(
        "/api/v1/auth/login", json={"email": "nina@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200


def test_an_invitation_works_once(client, db_session):
    _, token = auth.create_invitation(db_session, "nina@example.com", Role.VIEWER)
    assert accept(client, token).status_code == 201

    second = accept(client, token)
    assert second.status_code == 400
    assert second.json()["detail"] == "This invitation is invalid or has expired"


def test_unknown_token_gets_the_same_error(client):
    response = accept(client, "not-a-real-token")
    assert response.status_code == 400
    assert response.json()["detail"] == "This invitation is invalid or has expired"


def test_expired_invitation_is_rejected(client, db_session):
    _, token = auth.create_invitation(
        db_session, "nina@example.com", Role.VIEWER, hours=-1
    )
    assert accept(client, token).status_code == 400


def test_weak_password_keeps_the_invitation_usable(client, db_session):
    _, token = auth.create_invitation(db_session, "nina@example.com", Role.VIEWER)

    weak = accept(client, token, password="short")
    assert weak.status_code == 400
    assert "at least" in weak.json()["detail"]

    assert accept(client, token).status_code == 201  # same link, better password


def test_a_newer_invitation_replaces_the_older_link(client, db_session):
    _, old = auth.create_invitation(db_session, "nina@example.com", Role.VIEWER)
    _, new = auth.create_invitation(db_session, "nina@example.com", Role.VIEWER)

    assert accept(client, old).status_code == 400
    assert accept(client, new).status_code == 201
