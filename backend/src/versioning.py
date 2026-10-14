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
    rows = db.execute(
        select(ClientProfileVersion.version_number)
        .where(ClientProfileVersion.client_profile_id == client_profile_id)
        .with_for_update()
    ).scalars().all()

    return max(rows, default=0) + 1


def next_playbook_version(db: Session, playbook_id: uuid.UUID) -> int:
    """Return the next version number for a Playbook, holding a row lock.

    Locks all existing versions for this playbook so no concurrent transaction
    can insert a version between the read and the caller's insert.
    """
    rows = db.execute(
        select(PlaybookVersion.version_number)
        .where(PlaybookVersion.playbook_id == playbook_id)
        .with_for_update()
    ).scalars().all()

    return max(rows, default=0) + 1
