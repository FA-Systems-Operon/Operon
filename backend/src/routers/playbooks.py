"""Endpoints for creating and versioning playbooks."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Playbook, PlaybookVersion, ReviewStatus
from src.schemas import ApproveIn, PlaybookApprovalOut, PlaybookVersionOut
from src.staleness import mark_stale_for_playbook
from src.versioning import (
    get_latest_approved_playbook_version,
    next_playbook_version,
)

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=PlaybookVersionOut, status_code=status.HTTP_201_CREATED)
def create_playbook(db: DbSession) -> PlaybookVersion:
    """Create a new playbook and its first version."""
    playbook = Playbook()
    db.add(playbook)
    db.flush()  # assigns playbook.id without committing

    version = PlaybookVersion(
        playbook_id=playbook.id,
        version_number=1,
        data={},
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.put("/{playbook_id}", response_model=PlaybookVersionOut)
def update_playbook(
    playbook_id: uuid.UUID, data: dict, db: DbSession
) -> PlaybookVersion:
    """Create a new immutable version of a playbook instead of overwriting."""
    playbook = db.get(Playbook, playbook_id)
    if playbook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playbook not found")

    version_number = next_playbook_version(db, playbook_id)
    version = PlaybookVersion(
        playbook_id=playbook_id,
        version_number=version_number,
        data=data,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.get("/{playbook_id}/versions", response_model=list[PlaybookVersionOut])
def list_playbook_versions(
    playbook_id: uuid.UUID, db: DbSession
) -> list[PlaybookVersion]:
    """Return all versions of a playbook, oldest first."""
    playbook = db.get(Playbook, playbook_id)
    if playbook is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playbook not found")

    return sorted(playbook.versions, key=lambda v: v.version_number)


@router.get("/{playbook_id}/latest-approved", response_model=PlaybookVersionOut)
def latest_approved_playbook(playbook_id: uuid.UUID, db: DbSession) -> PlaybookVersion:
    """Return the highest approved version number, regardless of approval time."""
    if db.get(Playbook, playbook_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playbook not found")
    version = get_latest_approved_playbook_version(db, playbook_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No approved version found")
    return version


@router.post(
    "/{playbook_id}/versions/{version_id}/approve", response_model=PlaybookApprovalOut
)
def approve_playbook_version(
    playbook_id: uuid.UUID, version_id: uuid.UUID, body: ApproveIn, db: DbSession
) -> PlaybookApprovalOut:
    """approve and mark artifacts from older versions as stale
    get a lock using FOR UPDATE to avoid modifications
    """
    if db.get(Playbook, playbook_id, with_for_update=True) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playbook not found")
    version = db.scalar(
        select(PlaybookVersion)
        .where(
            PlaybookVersion.id == version_id,
            PlaybookVersion.playbook_id == playbook_id,
        )
        .with_for_update()
    )
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playbook version not found")
    if version.approved_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Version is already approved")

    version.status = ReviewStatus.APPROVED
    version.approved_by = body.approved_by
    version.approved_at = datetime.now(timezone.utc)
    db.flush()

    stale = mark_stale_for_playbook(db, playbook_id)
    db.commit()
    return PlaybookApprovalOut(
        version=PlaybookVersionOut.model_validate(version),
        newly_stale_artifact_version_ids=[a.id for a in stale],
    )
