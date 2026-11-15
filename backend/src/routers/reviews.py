"""The review inbox (#54) and the draft detail it opens (#57)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from src.auth import ReviewerUser
from src.db import get_db
from src.models import (
    Client,
    ClientProfile,
    ClientProfileVersion,
    ReviewStatus,
    SourceDocument,
)
from src.review_edits import (
    StaleReviewError,
    approve_review_draft,
    reject_review_draft,
    save_review_edits,
)
from src.schemas import (
    ClientProfileVersionOut,
    ProfileApprovalOut,
    ReviewDraftOut,
    ReviewEditsIn,
    ReviewInboxItemOut,
    ReviewRejectIn,
)

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/profiles/{profile_id}/versions/{version_id}/edits",
    response_model=ClientProfileVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def save_draft_edits(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ReviewEditsIn,
    db: DbSession,
    response: Response,
    _reviewer: ReviewerUser,
) -> ClientProfileVersion:
    """Validate corrections and append a draft, only if the base is still current."""
    try:
        version = save_review_edits(db, profile_id, version_id, body)
        db.commit()
    except LookupError as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except StaleReviewError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from error
    except Exception:
        db.rollback()
        raise
    db.refresh(version)
    if version.id == version_id:
        response.status_code = status.HTTP_200_OK
    return version


@router.post(
    "/profiles/{profile_id}/versions/{version_id}/reject",
    response_model=ClientProfileVersionOut,
)
def reject_draft(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ReviewRejectIn,
    db: DbSession,
    reviewer: ReviewerUser,
) -> ClientProfileVersion:
    """Reject the open draft with a short reason; no approved version is created."""
    try:
        version = reject_review_draft(db, profile_id, version_id, body, reviewer.id)
        db.commit()
    except LookupError as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except StaleReviewError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except Exception:
        db.rollback()
        raise
    db.refresh(version)
    return version


@router.post(
    "/profiles/{profile_id}/versions/{version_id}/approve",
    response_model=ProfileApprovalOut,
    status_code=status.HTTP_201_CREATED,
)
def approve_draft(
    profile_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbSession,
    reviewer: ReviewerUser,
) -> ProfileApprovalOut:
    """Save the open (possibly edited) draft as a new approved profile version."""
    try:
        version, stale = approve_review_draft(db, profile_id, version_id, reviewer.id)
        db.commit()
    except LookupError as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except StaleReviewError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from error
    except Exception:
        db.rollback()
        raise
    db.refresh(version)
    return ProfileApprovalOut(
        version=ClientProfileVersionOut.model_validate(version),
        newly_stale_artifact_version_ids=[a.id for a in stale],
    )


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


@router.get(
    "/profiles/{profile_id}/versions/{version_id}", response_model=ReviewDraftOut
)
def get_review_draft(
    profile_id: uuid.UUID, version_id: uuid.UUID, db: DbSession
) -> ReviewDraftOut:
    """Return one profile version with its client and that client's documents.

    Any version can be opened, not only ones awaiting review, so a draft that is
    approved while open still loads. The documents let the reviewer see which
    file each quote came from.
    """
    row = db.execute(
        select(ClientProfileVersion, Client)
        .join(ClientProfile, ClientProfile.id == ClientProfileVersion.client_profile_id)
        .join(Client, Client.id == ClientProfile.client_id)
        # Scoped to the profile: another profile's version is "not found" too.
        .where(
            ClientProfileVersion.id == version_id,
            ClientProfileVersion.client_profile_id == profile_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile version not found")
    version, client = row
    documents = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.client_id == client.id)
        .order_by(SourceDocument.uploaded_at, SourceDocument.id)
    )
    return ReviewDraftOut.model_validate(
        {"version": version, "client": client, "documents": list(documents)}
    )
