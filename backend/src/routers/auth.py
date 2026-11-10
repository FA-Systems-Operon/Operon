"""Endpoints for signing in and out, and for asking who is signed in."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from src import auth
from src.auth import AuthContext, DbSession
from src.models import Role, User

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=auth.MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    """The public view of a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: Role


class LoginOut(BaseModel):
    user: UserOut
    # Send this back in the X-CSRF-Token header on every POST, PUT, PATCH and DELETE.
    csrf_token: str


class InviteIn(BaseModel):
    email: str = Field(max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    expires_at: datetime
    # The one-time secret for the invite link. It is shown only in this response and is not
    # stored (only its hash is), so the admin has to copy the link now.
    invite_token: str


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=255)
    # Length rules are checked by the service so the message matches everywhere.
    password: str = Field(min_length=1, max_length=1000)


def _set_cookie(response: Response, name: str, value: str, http_only: bool) -> None:
    response.set_cookie(
        name,
        value,
        max_age=auth.SESSION_HOURS * 3600,
        httponly=http_only,
        secure=auth.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


@router.post("/auth/login", response_model=LoginOut)
def login(body: LoginIn, response: Response, db: DbSession) -> dict:
    """Sign in. Wrong email, wrong password and deactivated account all give the same answer.

    After too many failures for one email the answer is 429 until the lock lifts, even for
    the right password.
    """
    try:
        auth.check_login_allowed(db, body.email)
    except auth.TooManyAttempts as error:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(error.retry_after)},
        )

    user = auth.authenticate(db, body.email, body.password)
    if user is None:
        auth.record_failed_login(db, body.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    auth.clear_failed_logins(db, body.email)

    _, session_token, csrf_token = auth.create_session(db, user)
    _set_cookie(response, auth.SESSION_COOKIE, session_token, http_only=True)
    # JavaScript has to read this one to copy it into the header, so it is not HttpOnly.
    _set_cookie(response, auth.CSRF_COOKIE, csrf_token, http_only=False)
    return {"user": user, "csrf_token": csrf_token}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
        response: Response,
        db: DbSession,
        context: Annotated[AuthContext, Depends(auth.current_auth)],
) -> None:
    """Sign out. Needs the CSRF header like any other POST."""
    auth.revoke_session(db, context.session)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    response.delete_cookie(auth.CSRF_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(auth.current_user)]) -> User:
    """Who is signed in, and with which role."""
    return user


@router.post("/users/invite", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite_user(
        body: InviteIn,
        db: DbSession,
        admin: Annotated[User, Depends(auth.require_role(Role.ADMIN))],
) -> dict:
    """Admins only. Creates a one-time invite and returns its token once.

    Inviting an email again ends the older unused invite for it.
    """
    email = auth.normalize_email(body.email)
    if db.execute(select(User.id).where(User.email == email)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists")

    invitation, token = auth.create_invitation(db, email, body.role, invited_by=admin.id)
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.initial_role,
        "expires_at": invitation.expires_at,
        "invite_token": token,
    }


@router.post("/auth/accept-invite", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def accept_invite(body: AcceptInviteIn, db: DbSession) -> User:
    """Public. Turns a valid invite token into an account. Sign in afterwards."""
    try:
        return auth.accept_invitation(db, body.token, body.display_name, body.password)
    except auth.AuthError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error))
