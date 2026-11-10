import threading
import uuid
from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from src import auth as auth_module
from src.auth import (
    AuthError,
    accept_invitation,
    create_invitation,
    create_user,
    hash_password,
    hash_token,
    require_role,
    utcnow,
    verify_password,
)
from src.db import SessionLocal
from src.main import app
from src.models import Invitation, LoginAttempt, Role, User, UserSession

PASSWORD = "correct horse battery staple"


@pytest.fixture(scope="module", autouse=True)
def create_tables():
    with TestClient(app):  # app startup creates any missing tables
        yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)  # a fresh cookie jar for every test


def unique_email() -> str:
    return f"{uuid.uuid4().hex[:10]}@example.com"


def make_user(role: Role = Role.REVIEWER, password: str = PASSWORD, active: bool = True) -> str:
    email = unique_email()
    with SessionLocal() as db:
        user = create_user(db, email, "Test User", password, role)
        if not active:
            user.is_active = False
            db.commit()
    return email


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("operon_csrf")}


# --- passwords ---------------------------------------------------------------------


def test_password_is_hashed_and_verifiable():
    hashed = hash_password(PASSWORD)
    assert PASSWORD not in hashed
    assert verify_password(hashed, PASSWORD)
    assert not verify_password(hashed, "a different password!")


def test_the_same_password_gets_a_different_hash_each_time():
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_a_garbage_hash_never_verifies():
    assert not verify_password("not-a-hash", PASSWORD)


def test_a_short_password_is_refused():
    with SessionLocal() as db:
        with pytest.raises(AuthError, match="at least"):
            create_user(db, unique_email(), "Short", "short", Role.VIEWER)


# --- users and roles -----------------------------------------------------------------


def test_every_role_can_be_stored_and_read_back():
    for role in Role:
        email = make_user(role)
        with SessionLocal() as db:
            user = db.execute(select(User).where(User.email == email)).scalar_one()
            assert user.role == role
            assert user.is_active is True
            assert user.password_hash != PASSWORD


def test_emails_are_case_insensitive_and_unique():
    email = make_user()
    with SessionLocal() as db:
        with pytest.raises(AuthError, match="already exists"):
            create_user(db, email.upper(), "Duplicate", PASSWORD, Role.VIEWER)


# --- one-time invitations ------------------------------------------------------------


def test_only_the_hash_of_an_invite_token_is_stored():
    with SessionLocal() as db:
        invitation, token = create_invitation(db, unique_email(), Role.REVIEWER)
        assert invitation.token_hash == hash_token(token)
        assert invitation.token_hash != token
        assert len(invitation.token_hash) == 64


def test_an_invitation_creates_a_user_with_the_invited_role():
    email = unique_email()
    with SessionLocal() as db:
        _, token = create_invitation(db, email, Role.VIEWER)
        user = accept_invitation(db, token, "New Person", PASSWORD)
        assert user.email == email
        assert user.role == Role.VIEWER
        assert verify_password(user.password_hash, PASSWORD)


def test_an_invitation_works_only_once():
    with SessionLocal() as db:
        _, token = create_invitation(db, unique_email(), Role.REVIEWER)
        accept_invitation(db, token, "First", PASSWORD)
        with pytest.raises(AuthError, match="invalid or has expired"):
            accept_invitation(db, token, "Second", PASSWORD)


def test_an_expired_invitation_is_refused():
    with SessionLocal() as db:
        _, token = create_invitation(db, unique_email(), Role.REVIEWER, hours=-1)
        with pytest.raises(AuthError, match="invalid or has expired"):
            accept_invitation(db, token, "Late", PASSWORD)


def test_an_unknown_token_gets_the_same_error_as_a_used_one():
    with SessionLocal() as db:
        with pytest.raises(AuthError, match="invalid or has expired"):
            accept_invitation(db, "made-up-token", "Nobody", PASSWORD)


def test_a_refused_invitation_does_not_use_it_up():
    email = unique_email()
    with SessionLocal() as db:
        invitation, token = create_invitation(db, email, Role.REVIEWER)
        with pytest.raises(AuthError, match="at least"):
            accept_invitation(db, token, "Weak", "short")
        db.refresh(invitation)
        assert invitation.accepted_at is None
        accept_invitation(db, token, "Strong", PASSWORD)  # still works afterwards


def test_an_invitation_cannot_take_over_an_existing_account():
    email = make_user()
    with SessionLocal() as db:
        _, token = create_invitation(db, email, Role.ADMIN)
        with pytest.raises(AuthError, match="already exists"):
            accept_invitation(db, token, "Imposter", PASSWORD)


# --- login ---------------------------------------------------------------------------


def test_login_returns_the_user_and_sets_both_cookies(client):
    email = make_user(Role.REVIEWER)
    response = login(client, email)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "reviewer"
    assert body["csrf_token"] == client.cookies.get("operon_csrf")
    assert client.cookies.get("operon_session")
    assert "password" not in response.text


def test_cookie_flags(client):
    response = login(client, make_user())
    cookies = {c.split("=")[0]: c for c in response.headers.get_list("set-cookie")}
    session_cookie = cookies["operon_session"]
    csrf_cookie = cookies["operon_csrf"]
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "HttpOnly" not in csrf_cookie  # JavaScript has to read this one
    assert "SameSite=lax" in csrf_cookie


def test_wrong_password_and_unknown_email_look_the_same(client):
    email = make_user()
    wrong_password = login(client, email, "not the right password")
    unknown_email = login(client, unique_email())
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert not client.cookies.get("operon_session")


def test_a_deactivated_user_cannot_log_in(client):
    assert login(client, make_user(active=False)).status_code == 401


def test_login_ignores_email_capitalisation_and_spaces(client):
    email = make_user()
    assert login(client, f"  {email.upper()} ").status_code == 200


def test_only_hashes_of_the_session_and_csrf_tokens_are_stored(client):
    email = make_user()
    login(client, email)
    session_token = client.cookies.get("operon_session")
    csrf_token = client.cookies.get("operon_csrf")
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one()
        session = db.execute(
            select(UserSession).where(UserSession.user_id == user.id)
        ).scalar_one()
        assert session.token_hash == hash_token(session_token) != session_token
        assert session.csrf_token_hash == hash_token(csrf_token) != csrf_token
        assert session.expires_at > utcnow()
        assert session.revoked_at is None


# --- current user ----------------------------------------------------------------------


def test_me_needs_a_login(client):
    assert client.get("/api/v1/me").status_code == 401


def test_me_returns_the_signed_in_user(client):
    email = make_user(Role.ADMIN)
    login(client, email)
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == email
    assert response.json()["role"] == "admin"


def test_a_made_up_session_cookie_is_refused(client):
    client.cookies.set("operon_session", "made-up-value")
    assert client.get("/api/v1/me").status_code == 401


def test_an_expired_session_is_refused(client):
    email = make_user()
    login(client, email)
    with SessionLocal() as db:
        session = db.execute(
            select(UserSession).join(User).where(User.email == email)
        ).scalar_one()
        session.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get("/api/v1/me").status_code == 401


def test_a_deactivated_user_loses_access_on_the_next_request(client):
    email = make_user()
    login(client, email)
    assert client.get("/api/v1/me").status_code == 200
    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one()
        user.is_active = False
        db.commit()
    assert client.get("/api/v1/me").status_code == 401


# --- logout and CSRF ---------------------------------------------------------------------


def test_logout_without_the_csrf_header_is_refused_and_keeps_the_session(client):
    login(client, make_user())
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.get("/api/v1/me").status_code == 200


def test_logout_with_a_wrong_csrf_header_is_refused(client):
    login(client, make_user())
    response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "wrong"})
    assert response.status_code == 403


def test_a_csrf_token_from_another_session_is_refused(client):
    login(client, make_user())
    other = TestClient(app)
    login(other, make_user())
    # Cookie and header agree with each other, but the token was issued to a different session.
    client.cookies.set("operon_csrf", other.cookies.get("operon_csrf"))
    response = client.post("/api/v1/auth/logout", headers=csrf(other))
    assert response.status_code == 403


def test_logout_ends_the_session(client):
    email = make_user()
    login(client, email)
    stolen_cookie = client.cookies.get("operon_session")

    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 204
    assert client.get("/api/v1/me").status_code == 401

    # Even a copy of the old cookie is useless now.
    replay = TestClient(app)
    replay.cookies.set("operon_session", stolen_cookie)
    assert replay.get("/api/v1/me").status_code == 401
    with SessionLocal() as db:
        session = db.execute(
            select(UserSession).join(User).where(User.email == email)
        ).scalar_one()
        assert session.revoked_at is not None


# --- require_role: what other features will use ------------------------------------------

probe = FastAPI()


@probe.get("/admin-only")
def admin_only(user: User = Depends(require_role(Role.ADMIN))):
    return {"email": user.email}


@probe.post("/reviewer-action", dependencies=[Depends(require_role(Role.REVIEWER))])
def reviewer_action():
    return {"ok": True}


def probe_client_signed_in_as(role: Role) -> TestClient:
    real = TestClient(app)
    login(real, make_user(role))
    probe_client = TestClient(probe)
    probe_client.cookies.update(real.cookies)
    return probe_client


def test_require_role_answers_401_when_signed_out():
    assert TestClient(probe).get("/admin-only").status_code == 401


def test_require_role_answers_403_for_the_wrong_role():
    assert probe_client_signed_in_as(Role.VIEWER).get("/admin-only").status_code == 403
    assert probe_client_signed_in_as(Role.REVIEWER).get("/admin-only").status_code == 403


def test_require_role_lets_the_right_role_through():
    assert probe_client_signed_in_as(Role.ADMIN).get("/admin-only").status_code == 200


def test_an_admin_cannot_use_a_reviewer_only_action():
    assert probe_client_signed_in_as(Role.ADMIN).post("/reviewer-action").status_code in (403,)


def test_protected_posts_also_need_the_csrf_header():
    reviewer = probe_client_signed_in_as(Role.REVIEWER)
    assert reviewer.post("/reviewer-action").status_code == 403
    response = reviewer.post("/reviewer-action", headers=csrf(reviewer))
    assert response.status_code == 200


def test_require_role_with_no_roles_is_a_mistake():
    with pytest.raises(ValueError):
        require_role()


# --- invite endpoint (admins only) -------------------------------------------------------


def signed_in(role: Role) -> TestClient:
    client = TestClient(app)
    login(client, make_user(role))
    return client


def invite(client: TestClient, email: str | None = None, role: str = "reviewer"):
    return client.post(
        "/api/v1/users/invite",
        json={"email": email or unique_email(), "role": role},
        headers=csrf(client),
    )


def test_an_admin_can_invite_and_gets_the_token_once():
    admin = signed_in(Role.ADMIN)
    email = unique_email()
    response = invite(admin, email.upper(), "viewer")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "viewer"
    assert body["invite_token"]
    with SessionLocal() as db:
        stored = db.get(Invitation, uuid.UUID(body["id"]))
        assert stored.token_hash == hash_token(body["invite_token"])
        assert stored.token_hash != body["invite_token"]
        assert str(stored.invited_by) == admin.get("/api/v1/me").json()["id"]


def test_only_admins_can_invite():
    assert invite(signed_in(Role.REVIEWER)).status_code == 403
    assert invite(signed_in(Role.VIEWER)).status_code == 403


def test_inviting_needs_a_login_and_the_csrf_header():
    signed_out = TestClient(app).post(
        "/api/v1/users/invite", json={"email": unique_email(), "role": "viewer"}
    )
    assert signed_out.status_code == 401
    admin = signed_in(Role.ADMIN)
    no_csrf = admin.post(
        "/api/v1/users/invite", json={"email": unique_email(), "role": "viewer"}
    )
    assert no_csrf.status_code == 403


def test_inviting_an_existing_account_is_a_conflict():
    admin = signed_in(Role.ADMIN)
    assert invite(admin, make_user()).status_code == 409


def test_a_bad_email_or_role_is_refused():
    admin = signed_in(Role.ADMIN)
    assert invite(admin, "not-an-email").status_code == 422
    assert invite(admin, unique_email(), "superuser").status_code == 422


def test_inviting_the_same_email_again_cancels_the_older_link():
    admin = signed_in(Role.ADMIN)
    email = unique_email()
    first = invite(admin, email).json()["invite_token"]
    second = invite(admin, email).json()["invite_token"]
    public = TestClient(app)
    body = {"display_name": "Late Joiner", "password": PASSWORD}
    assert public.post("/api/v1/auth/accept-invite", json={"token": first, **body}).status_code == 400
    assert public.post("/api/v1/auth/accept-invite", json={"token": second, **body}).status_code == 201


# --- accept-invite endpoint (public) ---------------------------------------------------------


def accept(token: str, name: str = "New Person", password: str = PASSWORD):
    return TestClient(app).post(
        "/api/v1/auth/accept-invite",
        json={"token": token, "display_name": name, "password": password},
    )


def test_accepting_an_invite_creates_an_account_that_can_log_in():
    admin = signed_in(Role.ADMIN)
    email = unique_email()
    token = invite(admin, email, "reviewer").json()["invite_token"]

    response = accept(token, "Maya", "a brand new password")
    assert response.status_code == 201
    assert response.json()["email"] == email
    assert response.json()["role"] == "reviewer"
    assert "password" not in response.text

    newcomer = TestClient(app)
    assert login(newcomer, email, "a brand new password").status_code == 200
    assert newcomer.get("/api/v1/me").json()["display_name"] == "Maya"


def test_an_invite_link_works_only_once_over_http():
    token = invite(signed_in(Role.ADMIN)).json()["invite_token"]
    assert accept(token).status_code == 201
    assert accept(token).status_code == 400


def test_unknown_and_expired_invites_get_the_same_answer():
    with SessionLocal() as db:
        _, expired = create_invitation(db, unique_email(), Role.VIEWER, hours=-1)
    unknown = accept("made-up-token")
    late = accept(expired)
    assert unknown.status_code == late.status_code == 400
    assert unknown.json() == late.json()


def test_a_weak_password_or_blank_name_is_refused_and_keeps_the_invite_usable():
    token = invite(signed_in(Role.ADMIN)).json()["invite_token"]
    assert accept(token, password="short").status_code == 400
    assert accept(token, name="   ").status_code == 400
    assert accept(token).status_code == 201


def test_two_people_using_the_same_invite_at_once_only_one_wins():
    for _ in range(10):
        with SessionLocal() as db:
            _, token = create_invitation(db, unique_email(), Role.REVIEWER)
        results: list[str] = []
        barrier = threading.Barrier(2)

        def attempt(name: str) -> None:
            with SessionLocal() as db:
                barrier.wait()
                try:
                    accept_invitation(db, token, name, PASSWORD)
                    results.append("ok")
                except AuthError:
                    results.append("refused")

        threads = [threading.Thread(target=attempt, args=(n,)) for n in ("A", "B")]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert sorted(results) == ["ok", "refused"]


# --- slowing down password guessing -------------------------------------------------------------

def fail_login(client: TestClient, email: str, times: int) -> None:
    for _ in range(times):
        assert login(client, email, "the wrong password").status_code == 401


def count_failures(email: str) -> int:
    with SessionLocal() as db:
        return len(
            db.execute(select(LoginAttempt).where(LoginAttempt.email == email)).scalars().all()
        )


def test_too_many_failures_lock_the_email_even_for_the_right_password(client):
    email = make_user()
    fail_login(client, email, auth_module.LOGIN_MAX_FAILURES)

    locked = login(client, email)  # the correct password
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0
    assert not client.cookies.get("operon_session")


def test_the_lock_is_per_email(client):
    locked_email, other_email = make_user(), make_user()
    fail_login(client, locked_email, auth_module.LOGIN_MAX_FAILURES)
    assert login(client, other_email).status_code == 200


def test_unknown_emails_are_throttled_the_same_way(client):
    ghost = unique_email()
    fail_login(client, ghost, auth_module.LOGIN_MAX_FAILURES)
    assert login(client, ghost).status_code == 429


def test_a_successful_login_resets_the_count(client):
    email = make_user()
    fail_login(client, email, auth_module.LOGIN_MAX_FAILURES - 1)
    assert login(client, email).status_code == 200
    assert count_failures(email) == 0
    fail_login(client, email, auth_module.LOGIN_MAX_FAILURES - 1)  # still not locked


def test_refused_attempts_are_not_counted_so_the_lock_does_not_extend(client):
    email = make_user()
    fail_login(client, email, auth_module.LOGIN_MAX_FAILURES)
    for _ in range(3):
        assert login(client, email, "still wrong").status_code == 429
    assert count_failures(email) == auth_module.LOGIN_MAX_FAILURES


def test_the_lock_lifts_after_the_window(client):
    email = make_user()
    fail_login(client, email, auth_module.LOGIN_MAX_FAILURES)
    assert login(client, email).status_code == 429

    long_ago = utcnow() - timedelta(minutes=auth_module.LOGIN_WINDOW_MINUTES + 1)
    with SessionLocal() as db:
        for attempt in db.execute(
                select(LoginAttempt).where(LoginAttempt.email == email)
        ).scalars():
            attempt.attempted_at = long_ago
        db.commit()
    assert login(client, email).status_code == 200
