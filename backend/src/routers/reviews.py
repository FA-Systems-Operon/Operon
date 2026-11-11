"""The review inbox: generated profile drafts waiting for a reviewer (#54)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Client, ClientProfile, ClientProfileVersion, ReviewStatus
from src.schemas import ReviewInboxItemOut

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[ReviewInboxItemOut])
def list_review_inbox(db: DbSession) -> list[ReviewInboxItemOut]:
    """Return the latest version of each profile while it awaits review, newest first.

    An older draft with a newer version is superseded, so only the latest counts.
    The empty {} version 1 that POST /client-profiles creates is not a draft to
    review; every generated or edited draft has data, so empty data is left out.
    """
    latest = (
        select(
            ClientProfileVersion.client_profile_id,
            func.max(ClientProfileVersion.version_number).label("version_number"),
        )
        .group_by(ClientProfileVersion.client_profile_id)
        .subquery()
    )
    query = (
        select(
            ClientProfileVersion.id.label("version_id"),
            ClientProfileVersion.client_profile_id,
            ClientProfileVersion.version_number,
            ClientProfile.client_id,
            Client.name.label("client_name"),
            ClientProfileVersion.created_at,
            ClientProfileVersion.status,
        )
        .join(
            latest,
            (latest.c.client_profile_id == ClientProfileVersion.client_profile_id)
            & (latest.c.version_number == ClientProfileVersion.version_number),
        )
        .join(ClientProfile, ClientProfile.id == ClientProfileVersion.client_profile_id)
        .join(Client, Client.id == ClientProfile.client_id)
        .where(
            ClientProfileVersion.status.in_(
                [ReviewStatus.DRAFT, ReviewStatus.IN_REVIEW]
            ),
            ClientProfileVersion.data != literal({}, JSONB),
        )
        # id breaks ties between versions saved in the same transaction.
        .order_by(
            ClientProfileVersion.created_at.desc(), ClientProfileVersion.id.desc()
        )
    )
    return [ReviewInboxItemOut.model_validate(row) for row in db.execute(query)]
