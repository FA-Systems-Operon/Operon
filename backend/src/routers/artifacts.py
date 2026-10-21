import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from src.db import get_db
from src.models import (
    Artifact,
    ArtifactVersion,
    Client,
    ClientProfile,
    ClientProfileVersion,
    Playbook,
    PlaybookVersion,
    ReviewStatus,
)
from src.schemas import (
    ApproveIn,
    ArtifactCreate,
    ArtifactVersionCreate,
    ArtifactVersionOut,
)
from src.staleness import _mark, is_artifact_stale
from src.versioning import (
    get_latest_approved_client_profile_version,
    get_latest_approved_playbook_version,
    next_artifact_version,
)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

DbSession = Annotated[Session, Depends(get_db)]


def _lock_and_check_inputs(
    db: Session,
    client_id: uuid.UUID,
    profile_version_id: uuid.UUID,
    playbook_version_id: uuid.UUID | None,
) -> None:
    """Lock the parent rows, artifact cant become non-stale"""
    pv = db.get(ClientProfileVersion, profile_version_id)
    if pv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile version not found")
    profile = db.get(ClientProfile, pv.client_profile_id, with_for_update=True)
    if profile is None or profile.client_id != client_id:
        # dont leak client version info
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile version not found")
    if pv.approved_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Profile version is not approved")
    latest = get_latest_approved_client_profile_version(db, profile.id)
    if latest is None or latest.id != pv.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Profile version has been superseded by a newer approved version",
        )

    if playbook_version_id is not None:
        pbv = db.get(PlaybookVersion, playbook_version_id)
        if pbv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Playbook version not found")
        db.get(Playbook, pbv.playbook_id, with_for_update=True)
        if pbv.approved_at is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Playbook version is not approved"
            )
        latest_pb = get_latest_approved_playbook_version(db, pbv.playbook_id)
        if latest_pb is None or latest_pb.id != pbv.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Playbook version has been superseded by a newer approved version",
            )


@router.post("", response_model=ArtifactVersionOut, status_code=status.HTTP_201_CREATED)
def create_artifact(body: ArtifactCreate, db: DbSession) -> ArtifactVersion:
    """Create an artifact and its first draft version, pinned to approved inputs."""
    if db.get(Client, body.client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    _lock_and_check_inputs(
        db, body.client_id, body.client_profile_version_id, body.playbook_version_id
    )
    artifact = Artifact(client_id=body.client_id, kind=body.kind)
    db.add(artifact)
    db.flush()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        version_number=1,
        data=body.data,
        client_profile_version_id=body.client_profile_version_id,
        playbook_version_id=body.playbook_version_id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.post(
    "/{artifact_id}/versions",
    response_model=ArtifactVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_artifact_version(
    artifact_id: uuid.UUID, body: ArtifactVersionCreate, db: DbSession
) -> ArtifactVersion:
    """Regenerate/edit an artifact as a NEW version (how a stale one is re-reviewed)."""
    artifact = db.get(Artifact, artifact_id, with_for_update=True)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    _lock_and_check_inputs(
        db, artifact.client_id, body.client_profile_version_id, body.playbook_version_id
    )
    version = ArtifactVersion(
        artifact_id=artifact_id,
        version_number=next_artifact_version(db, artifact_id),
        data=body.data,
        client_profile_version_id=body.client_profile_version_id,
        playbook_version_id=body.playbook_version_id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


# Declared before "/{artifact_id}/..." routes so "stale" isn't parsed as a UUID.
@router.get("/stale", response_model=list[ArtifactVersionOut])
def list_stale_artifacts(
    db: DbSession, client_id: uuid.UUID | None = None
) -> list[ArtifactVersion]:
    """Stale versions awaiting re-review.

    A stale version is hidden once a newer version of the same artifact exists
    (it has been picked up); it stays in the full history either way.
    """
    newer = aliased(ArtifactVersion)
    query = (
        select(ArtifactVersion)
        .join(Artifact, Artifact.id == ArtifactVersion.artifact_id)
        .where(
            ArtifactVersion.status == ReviewStatus.STALE,
            ~exists().where(
                newer.artifact_id == ArtifactVersion.artifact_id,
                newer.version_number > ArtifactVersion.version_number,
            ),
        )
        .order_by(ArtifactVersion.stale_at)
    )
    if client_id is not None:
        query = query.where(Artifact.client_id == client_id)
    return list(db.scalars(query))


@router.get("/{artifact_id}/versions", response_model=list[ArtifactVersionOut])
def list_artifact_versions(
    artifact_id: uuid.UUID, db: DbSession
) -> list[ArtifactVersion]:
    """Full history, oldest first, including stale and rejected versions."""
    if db.get(Artifact, artifact_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")
    return list(
        db.scalars(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact_id)
            .order_by(ArtifactVersion.version_number)
        )
    )


@router.post(
    "/{artifact_id}/versions/{version_id}/approve", response_model=ArtifactVersionOut
)
def approve_artifact_version(
    artifact_id: uuid.UUID, version_id: uuid.UUID, body: ApproveIn, db: DbSession
) -> ArtifactVersion:
    """Approve an artifact version, but only if its inputs are still current."""
    artifact = db.get(Artifact, artifact_id, with_for_update=True)
    version = db.get(ArtifactVersion, version_id)
    if artifact is None or version is None or version.artifact_id != artifact_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact version not found")
    if version.status not in (ReviewStatus.DRAFT, ReviewStatus.IN_REVIEW):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot approve a {version.status.value} version"
        )

    # Lock the same parent rows the approve endpoints lock, then re-check.
    pv = db.get(ClientProfileVersion, version.client_profile_version_id)
    db.get(ClientProfile, pv.client_profile_id, with_for_update=True)
    if version.playbook_version_id is not None:
        pbv = db.get(PlaybookVersion, version.playbook_version_id)
        db.get(Playbook, pbv.playbook_id, with_for_update=True)

    if is_artifact_stale(
        db, version.client_profile_version_id, version.playbook_version_id
    ):
        _mark([version], "Inputs were superseded before this version was approved.")
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Inputs are out of date; this version is now stale. "
            "Create a new version from the current approved context.",
        )

    version.status = ReviewStatus.APPROVED
    version.approved_by = body.approved_by
    version.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(version)
    return version
