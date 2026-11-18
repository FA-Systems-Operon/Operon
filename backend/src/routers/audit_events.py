"""The audit log view for admins (#71): read-only, newest first, one page at a time."""

import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, tuple_

from src.auth import DbSession, require_role
from src.models import (
    AuditEvent,
    Client,
    ClientProfile,
    ClientProfileVersion,
    OnboardingJob,
    Role,
    SourceDocument,
    User,
)
from src.schemas import AuditEventOut, AuditEventPageOut

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])

AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


# Pages are keyed on (created_at, id), not an offset: events recorded while an admin
# reads would otherwise shift every later page and repeat rows. Several events saved
# in one transaction share created_at, so id breaks the tie.
def encode_cursor(created_at: datetime, event_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{event_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at, event_id = raw.split("|")
        parsed = datetime.fromisoformat(created_at)
        if parsed.tzinfo is None:
            raise ValueError("cursor time has no time zone")
        return parsed, uuid.UUID(event_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid cursor") from error


@router.get("", response_model=AuditEventPageOut)
def list_audit_events(
    db: DbSession,
    _admin: AdminUser,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> AuditEventPageOut:
    """Return recorded events newest first. Admins only.

    object_id points at a different table for each object_type, so each is looked up
    with its own outer join; a row that no longer exists just leaves the names empty.
    """
    profile_client = select(ClientProfile.id, ClientProfile.client_id).subquery(
        "profile_client"
    )
    document = select(
        SourceDocument.id, SourceDocument.client_id, SourceDocument.original_filename
    ).subquery("document")
    job = select(OnboardingJob.id, OnboardingJob.client_id).subquery("job")

    client_id = func.coalesce(
        profile_client.c.client_id, document.c.client_id, job.c.client_id
    )
    query = (
        select(
            AuditEvent.id,
            AuditEvent.created_at,
            AuditEvent.action,
            AuditEvent.actor_id,
            User.display_name.label("actor_name"),
            User.email.label("actor_email"),
            AuditEvent.object_type,
            AuditEvent.object_id,
            AuditEvent.version_id,
            client_id.label("client_id"),
            Client.name.label("client_name"),
            ClientProfileVersion.version_number,
            document.c.original_filename.label("document_filename"),
        )
        .join(User, User.id == AuditEvent.actor_id)
        .outerjoin(
            profile_client,
            (AuditEvent.object_type == "client_profile")
            & (profile_client.c.id == AuditEvent.object_id),
        )
        .outerjoin(
            document,
            (AuditEvent.object_type == "source_document")
            & (document.c.id == AuditEvent.object_id),
        )
        .outerjoin(
            job,
            (AuditEvent.object_type == "onboarding_job")
            & (job.c.id == AuditEvent.object_id),
        )
        .outerjoin(Client, Client.id == client_id)
        .outerjoin(
            ClientProfileVersion,
            ClientProfileVersion.id == AuditEvent.version_id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        # One extra row tells us whether another page exists.
        .limit(limit + 1)
    )
    if cursor is not None:
        query = query.where(
            tuple_(AuditEvent.created_at, AuditEvent.id) < decode_cursor(cursor)
        )

    rows = db.execute(query).mappings().all()
    page = [AuditEventOut(**row) for row in rows[:limit]]
    next_cursor = (
        encode_cursor(page[-1].created_at, page[-1].id) if len(rows) > limit else None
    )
    return AuditEventPageOut(items=page, next_cursor=next_cursor)
