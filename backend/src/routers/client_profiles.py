"""Endpoints for creating and versioning client profiles."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ai.source_prompt import SourceLinkedProfile
from src.db import get_db
from src.models import ClientProfile, ClientProfileVersion, ReviewStatus
from src.profile_sources import save_source_profile
from src.schemas import ApproveIn, ClientProfileVersionOut, ProfileApprovalOut
from src.staleness import mark_stale_for_client_profile
from src.versioning import (
    get_latest_approved_client_profile_version,
    next_client_profile_version,
)

router = APIRouter(prefix="/client-profiles", tags=["client-profiles"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "", response_model=ClientProfileVersionOut, status_code=status.HTTP_201_CREATED
)
def create_client_profile(client_id: uuid.UUID, db: DbSession) -> ClientProfileVersion:
    """Create a new client profile and its first version."""
    profile = ClientProfile(client_id=client_id)
    db.add(profile)
    db.flush()  # assigns profile.id without committing

    version = ClientProfileVersion(
        client_profile_id=profile.id,
        version_number=1,
        data={},
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.put("/{profile_id}", response_model=ClientProfileVersionOut)
def update_client_profile(
    profile_id: uuid.UUID, data: dict, db: DbSession
) -> ClientProfileVersion:
    """Create a new immutable version of a client profile instead of overwriting."""
    profile = db.get(ClientProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client profile not found")

    version_number = next_client_profile_version(db, profile_id)
    version = ClientProfileVersion(
        client_profile_id=profile_id,
        version_number=version_number,
        data=data,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.post(
    "/{profile_id}/source-drafts",
    response_model=ClientProfileVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_source_draft(
    profile_id: uuid.UUID, body: SourceLinkedProfile, db: DbSession
) -> ClientProfileVersion:
    """Save a generated draft only when its evidence matches stored client text."""
    try:
        version = save_source_profile(db, profile_id, body)
        db.commit()
    except LookupError as error:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)
        ) from error
    except Exception:
        db.rollback()
        raise
    db.refresh(version)
    return version


@router.get("/{profile_id}/versions", response_model=list[ClientProfileVersionOut])
def list_client_profile_versions(
    profile_id: uuid.UUID, db: DbSession
) -> list[ClientProfileVersion]:
    """Return all versions of a client profile, oldest first."""
    profile = db.get(ClientProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client profile not found")

    return sorted(profile.versions, key=lambda v: v.version_number)


@router.get("/{profile_id}/latest-approved", response_model=ClientProfileVersionOut)
def latest_approved_client_profile(
    profile_id: uuid.UUID, db: DbSession
) -> ClientProfileVersion:
    """Return the highest approved version number, regardless of approval time."""
    if db.get(ClientProfile, profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client profile not found")
    version = get_latest_approved_client_profile_version(db, profile_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No approved version found")
    return version


@router.post(
    "/{profile_id}/versions/{version_id}/approve", response_model=ProfileApprovalOut
)
def approve_client_profile_version(
    profile_id: uuid.UUID, version_id: uuid.UUID, body: ApproveIn, db: DbSession
) -> ProfileApprovalOut:
    """Approve one version, then mark artifacts built from older versions stale.

    Approval and staleness marking commit in ONE transaction, so there is never
    a moment where a newer profile is approved but old outputs look current.
    """
    # Same lock the artifact endpoints take; serialises approve vs. create.
    if db.get(ClientProfile, profile_id, with_for_update=True) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client profile not found")
    version = db.scalar(
        select(ClientProfileVersion)
        .where(
            ClientProfileVersion.id == version_id,
            ClientProfileVersion.client_profile_id == profile_id,
        )
        .with_for_update()
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile version not found")
    if version.approved_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Version is already approved")

    version.status = ReviewStatus.APPROVED
    version.approved_by = body.approved_by
    version.approved_at = datetime.now(timezone.utc)
    db.flush()

    stale = mark_stale_for_client_profile(db, profile_id)
    db.commit()
    return ProfileApprovalOut(
        version=ClientProfileVersionOut.model_validate(version),
        newly_stale_artifact_version_ids=[a.id for a in stale],
    )
