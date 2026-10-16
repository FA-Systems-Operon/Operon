"""Transactional version numbering for immutable version records.

Uses SELECT FOR UPDATE to lock existing version rows before reading the max,
so concurrent requests cannot both read the same max and produce duplicate
version numbers.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import ClientProfileVersion, PlaybookVersion


def next_client_profile_version(db: Session, client_profile_id: uuid.UUID) -> int:
    """Return the next version number for a ClientProfile, holding a row lock.

    Locks all existing versions for this profile so no concurrent transaction
    can insert a version between the read and the caller's insert.
    """
    rows = (
        db.execute(
            select(ClientProfileVersion.version_number)
            .where(ClientProfileVersion.client_profile_id == client_profile_id)
            .with_for_update()
        )
        .scalars()
        .all()
    )

    return max(rows, default=0) + 1


def next_playbook_version(db: Session, playbook_id: uuid.UUID) -> int:
    """Return the next version number for a Playbook, holding a row lock.

    Locks all existing versions for this playbook so no concurrent transaction
    can insert a version between the read and the caller's insert.
    """
    rows = (
        db.execute(
            select(PlaybookVersion.version_number)
            .where(PlaybookVersion.playbook_id == playbook_id)
            .with_for_update()
        )
        .scalars()
        .all()
    )

    return max(rows, default=0) + 1


def get_latest_approved_client_profile_version(
    db: Session, client_profile_id: uuid.UUID
) -> ClientProfileVersion | None:
    """Return the highest numbered approved snapshot, or None if none exists.

    Approval time is metadata, not ordering: approving an older version later
    must not roll back the current approved record. ID breaks legacy duplicate
    version-number ties deterministically.
    """
    return db.scalar(
        select(ClientProfileVersion)
        .where(
            ClientProfileVersion.client_profile_id == client_profile_id,
            ClientProfileVersion.approved_at.is_not(None),
        )
        .order_by(
            ClientProfileVersion.version_number.desc(), ClientProfileVersion.id.desc()
        )
        .limit(1)
    )


def get_latest_approved_playbook_version(
    db: Session, playbook_id: uuid.UUID
) -> PlaybookVersion | None:
    """Return the highest numbered approved snapshot, or None if none exists.

    Approval time is metadata, not ordering: approving an older version later
    must not roll back the current approved record. ID breaks legacy duplicate
    version-number ties deterministically.
    """
    return db.scalar(
        select(PlaybookVersion)
        .where(
            PlaybookVersion.playbook_id == playbook_id,
            PlaybookVersion.approved_at.is_not(None),
        )
        .order_by(PlaybookVersion.version_number.desc(), PlaybookVersion.id.desc())
        .limit(1)
    )
