import hashlib
import hmac
import math
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Invitation, LoginAttempt, Role, User, UserSession

# --- settings (environment variables, with safe defaults for local development) -----

SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "8"))
INVITE_HOURS = int(os.environ.get("INVITE_HOURS", "72"))
# Must be true when the site is served over HTTPS (set it in the production compose file).
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

# After this many failed logins for one email, further attempts are refused for a while.
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOGIN_WINDOW_MINUTES = int(os.environ.get("LOGIN_WINDOW_MINUTES", "15"))

SESSION_COOKIE = "operon_session"  # HttpOnly: JavaScript cannot read it
CSRF_COOKIE = (
    "operon_csrf"  # readable by JavaScript, which copies it into the header below
)
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128  # stops someone sending a huge "password" to burn CPU

_hasher = PasswordHasher()  # Argon2id with the library's recommended settings
# Checked when the email is unknown, so "no such user" takes as long as "wrong password".
_DUMMY_HASH = _hasher.hash("not-a-real-password")


class AuthError(Exception):
    """A sign-up or invitation rule was broken. The message is safe to show the user."""


class TooManyAttempts(Exception):
    """Too many failed logins for one email. retry_after is in seconds."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many failed login attempts")
        self.retry_after = retry_after


# --- small helpers --------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def new_token() -> str:
    """A random, unguessable token (256 bits). Give it to the user once, store only its hash."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Plain SHA-256 is fine here: the tokens are random, not human-chosen like passwords.
    return hashlib.sha256(token.encode()).hexdigest()


# --- passwords ------------------------------------------------------------------------


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# --- users and invitations ------------------------------------------------------------


def create_user(
    db: Session,
    email: str,
    display_name: str,
    password: str,
    role: Role,
    commit: bool = True,
) -> User:
    """Create an active user. Raises AuthError for a weak password, no name or a taken email.

    With commit=False the user is only flushed, so the caller can finish more work and
    commit everything together (accept_invitation does this).
    """
    validate_password(password)
    if not display_name.strip():
        raise AuthError("Name is required")
    email = normalize_email(email)
    if db.execute(select(User.id).where(User.email == email)).first() is not None:
        raise AuthError("An account with that email already exists")
    user = User(
        email=email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    try:
        db.flush()
        if commit:
            db.commit()
    except IntegrityError:  # someone created the same email a split second ago
        db.rollback()
        raise AuthError("An account with that email already exists")
    return user


def create_invitation(
    db: Session,
    email: str,
    role: Role,
    invited_by: uuid.UUID | None = None,
    hours: int = INVITE_HOURS,
) -> tuple[Invitation, str]:
    """Create a one-time invite. Returns (invitation, token). The token is shown only now.

    Inviting the same email again ends any older unused invite for it, so only the newest
    link works.
    """
    email = normalize_email(email)
    now = utcnow()
    db.execute(
        update(Invitation)
        .where(
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > now,
        )
        .values(expires_at=now)
    )
    token = new_token()
    invitation = Invitation(
        email=email,
        initial_role=role,
        token_hash=hash_token(token),
        invited_by=invited_by,
        expires_at=now + timedelta(hours=hours),
    )
    db.add(invitation)
    db.commit()
    return invitation, token


def accept_invitation(
    db: Session, token: str, display_name: str, password: str
) -> User:
    """Use an invite to create the account. Works once; unknown, used and expired look the same."""
    invalid = AuthError("This invitation is invalid or has expired")
    validate_password(password)

    # Lock the row until we commit, so two people using the same link at the same moment
    # cannot both succeed. The user and the "used" mark are saved in one transaction.
    invitation = db.execute(
        select(Invitation)
        .where(Invitation.token_hash == hash_token(token))
        .with_for_update()
    ).scalar_one_or_none()
    if invitation is None or invitation.accepted_at is not None:
        db.rollback()
        raise invalid
    if invitation.expires_at <= utcnow():
        db.rollback()
        raise invalid

    try:
        user = create_user(
            db,
            invitation.email,
            display_name,
            password,
            invitation.initial_role,
            commit=False,
        )
    except AuthError:
        db.rollback()  # release the lock; the invite stays unused
        raise
    invitation.accepted_at = utcnow()
    db.commit()
    return user


# --- signing in -----------------------------------------------------------------------


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user if the email and password are right and the account is active."""
    user = db.execute(
        select(User).where(User.email == normalize_email(email))
    ).scalar_one_or_none()
    if user is None:
        verify_password(_DUMMY_HASH, password)  # spend the same time as a real check
        return None
    if not verify_password(user.password_hash, password) or not user.is_active:
        return None
    return user


# --- slowing down password guessing ------------------------------------------------------
# Failed logins are counted per email (not per IP: behind the proxy every user shares one IP).
# While an email is over the limit, even the right password is refused. Refused attempts are
# not counted, so the lock always ends LOGIN_WINDOW_MINUTES after the oldest counted failure.
# The same rule applies to emails with no account, so the answer never reveals whether one exists.


def check_login_allowed(db: Session, email: str) -> None:
    """Raise TooManyAttempts if this email has used up its failed logins."""
    now = utcnow()
    window = timedelta(minutes=LOGIN_WINDOW_MINUTES)
    failures = (
        db.execute(
            select(LoginAttempt.attempted_at)
            .where(
                LoginAttempt.email == normalize_email(email),
                LoginAttempt.attempted_at > now - window,
            )
            .order_by(LoginAttempt.attempted_at)
        )
        .scalars()
        .all()
    )
    if len(failures) >= LOGIN_MAX_FAILURES:
        lifts_at = failures[len(failures) - LOGIN_MAX_FAILURES] + window
        raise TooManyAttempts(max(1, math.ceil((lifts_at - now).total_seconds())))


def record_failed_login(db: Session, email: str) -> None:
    now = utcnow()
    db.add(LoginAttempt(email=normalize_email(email), attempted_at=now))
    # Housekeeping: nothing older than a day is ever needed.
    db.execute(
        delete(LoginAttempt).where(LoginAttempt.attempted_at < now - timedelta(days=1))
    )
    db.commit()


def clear_failed_logins(db: Session, email: str) -> None:
    """A successful login starts the count again."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.email == normalize_email(email)))
    db.commit()


def create_session(db: Session, user: User) -> tuple[UserSession, str, str]:
    """Start a session. Returns (session, session_token, csrf_token); hand the tokens to the browser."""
    session_token = new_token()
    csrf_token = new_token()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=utcnow() + timedelta(hours=SESSION_HOURS),
    )
    db.add(session)
    db.commit()
    return session, session_token, csrf_token


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = utcnow()
    db.commit()


# --- FastAPI dependencies -------------------------------------------------------------

DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class AuthContext:
    user: User
    session: UserSession


def _not_signed_in() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


def _check_csrf(request: Request, session: UserSession) -> None:
    """The header must match the CSRF cookie AND be the token issued to this session."""
    header = request.headers.get(CSRF_HEADER)
    cookie = request.cookies.get(CSRF_COOKIE)
    if (
        not header
        or not cookie
        or not hmac.compare_digest(header, cookie)
        or not hmac.compare_digest(hash_token(header), session.csrf_token_hash)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")


def current_auth(request: Request, db: DbSession) -> AuthContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _not_signed_in()

    session = db.execute(
        select(UserSession).where(UserSession.token_hash == hash_token(token))
    ).scalar_one_or_none()
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= utcnow()
    ):
        raise _not_signed_in()

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:  # deactivated users lose access immediately
        raise _not_signed_in()

    if request.method not in SAFE_METHODS:
        _check_csrf(request, session)
    return AuthContext(user=user, session=session)


def current_user(auth: Annotated[AuthContext, Depends(current_auth)]) -> User:
    return auth.user


def require_role(*roles: Role):
    """Dependency factory: signed in AND one of these roles, otherwise 401 or 403."""
    if not roles:
        raise ValueError("require_role needs at least one role")

    def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this")
        return user

    return check
