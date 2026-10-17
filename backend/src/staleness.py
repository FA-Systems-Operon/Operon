import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import (
    ArtifactVersion,
    ClientProfileVersion,
    PlaybookVersion,
    ReviewStatus,
)
from src.versioning import (
    get_latest_approved_client_profile_version,
    get_latest_approved_playbook_version,
)

# Already terminal for this purpose: don't re-stamp or resurrect these.
_SKIP = (ReviewStatus.STALE, ReviewStatus.REJECTED)


def is_artifact_stale(
    db: Session,
    profile_version_id: uuid.UUID,
    playbook_version_id: uuid.UUID | None = None,
) -> bool:
    """Check whether an artifact's source versions are still the current approved ones."""
    profile_used = db.get(ClientProfileVersion, profile_version_id)
    if profile_used is None:
        return True

    latest_profile = get_latest_approved_client_profile_version(
        db, profile_used.client_profile_id
    )
    if latest_profile is None or latest_profile.id != profile_used.id:
        return True

    if playbook_version_id is not None:
        playbook_used = db.get(PlaybookVersion, playbook_version_id)
        if playbook_used is None:
            return True
        latest_playbook = get_latest_approved_playbook_version(
            db, playbook_used.playbook_id
        )
        if latest_playbook is None or latest_playbook.id != playbook_used.id:
            return True

    return False


def _mark(rows: list[ArtifactVersion], reason: str) -> list[ArtifactVersion]:
    now = datetime.now(timezone.utc)
    for av in rows:
        av.status = ReviewStatus.STALE
        av.stale_at = now
        av.stale_reason = reason
    return rows


def mark_stale_for_client_profile(
    db: Session, client_profile_id: uuid.UUID
) -> list[ArtifactVersion]:
    latest = get_latest_approved_client_profile_version(db, client_profile_id)
    if latest is None:
        return []
    older_ids = select(ClientProfileVersion.id).where(
        ClientProfileVersion.client_profile_id == client_profile_id,
        ClientProfileVersion.id != latest.id,
    )
    rows = list(
        db.scalars(
            select(ArtifactVersion)
            .where(
                ArtifactVersion.client_profile_version_id.in_(older_ids),
                ArtifactVersion.status.not_in(_SKIP),
            )
            .with_for_update()
        )
    )
    return _mark(
        rows,
        f"Client profile version {latest.version_number} ({latest.id}) was approved; "
        "this was built from an older version.",
    )


def mark_stale_for_playbook(
    db: Session, playbook_id: uuid.UUID
) -> list[ArtifactVersion]:
    latest = get_latest_approved_playbook_version(db, playbook_id)
    if latest is None:
        return []
    older_ids = select(PlaybookVersion.id).where(
        PlaybookVersion.playbook_id == playbook_id,
        PlaybookVersion.id != latest.id,
    )
    rows = list(
        db.scalars(
            select(ArtifactVersion)
            .where(
                ArtifactVersion.playbook_version_id.in_(older_ids),
                ArtifactVersion.status.not_in(_SKIP),
            )
            .with_for_update()
        )
    )
    return _mark(
        rows,
        f"Playbook version {latest.version_number} ({latest.id}) was approved; "
        "this was built from an older version.",
    )
