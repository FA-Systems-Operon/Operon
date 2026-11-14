"""Save bounded reviewer corrections without reinterpreting original evidence."""

import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import ClientProfile, ClientProfileVersion, ReviewStatus
from src.profile_flags import SCALAR_FIELDS
from src.schemas import ReviewEditsIn, ReviewRejectIn
from src.versioning import next_client_profile_version


class StaleReviewError(Exception):
    """The loaded version is no longer the editable profile head."""


def _lock_editable_head(
    db: Session, profile_id: uuid.UUID, version_id: uuid.UUID
) -> ClientProfileVersion:
    """Lock the profile and return the version only if it is the open draft head."""
    if db.get(ClientProfile, profile_id, with_for_update=True) is None:
        raise LookupError("Client profile not found")
    base = db.scalar(
        select(ClientProfileVersion).where(
            ClientProfileVersion.client_profile_id == profile_id,
            ClientProfileVersion.id == version_id,
        )
    )
    if base is None:
        raise LookupError("Profile version not found")
    latest_id = db.scalar(
        select(ClientProfileVersion.id)
        .where(ClientProfileVersion.client_profile_id == profile_id)
        .order_by(ClientProfileVersion.version_number.desc())
        .limit(1)
    )
    if (
        latest_id != base.id
        or base.status not in (ReviewStatus.DRAFT, ReviewStatus.IN_REVIEW)
        or base.approved_at is not None
    ):
        raise StaleReviewError("Draft changed or is no longer editable. Reload it.")
    return base


def save_review_edits(
    db: Session, profile_id: uuid.UUID, version_id: uuid.UUID, body: ReviewEditsIn
) -> ClientProfileVersion:
    """Caller owns commit/rollback; hold the parent lock through the commit."""
    base = _lock_editable_head(db, profile_id, version_id)
    if not isinstance(base.data, dict):
        raise ValueError("Draft data must be a JSON object")  # noqa: TRY004 -- maps to 422
    data = deepcopy(base.data)
    changed_nonnull_paths: list[str] = []
    for path, raw_value in body.changes.items():
        value = (raw_value.strip() or None) if raw_value is not None else None
        if path in SCALAR_FIELDS:
            if data.get(path) != value and value is not None:
                changed_nonnull_paths.append(path)
            data[path] = value
            continue
        match = re.fullmatch(r"(needs|goals)/(0|[1-9][0-9]*)", path)
        if match is None:
            raise ValueError("Only editable profile fields may be changed")
        group, index_text = match.groups()
        items = data.get(group)
        index = int(index_text)
        if not isinstance(items, list) or index >= len(items):
            raise ValueError("Only existing list items may be changed")
        if not isinstance(items[index], str) or value is None:
            raise ValueError(
                "List edits require an existing text item and nonblank value"
            )
        if items[index] != value:
            changed_nonnull_paths.append(path)
        items[index] = value

    if data == base.data:
        return base

    # Remove only existing missing claims for actual non-null corrections. Clearing
    # a value preserves its recorded marker; never add new missing claims here.
    # Conflict/evidence history is unchanged. Unknown assessments stay as-is.
    assessment = data.get("assessment")
    if (
        isinstance(assessment, dict)
        and assessment.get("rules_version") == 1
        and isinstance(assessment.get("missing_fields"), list)
    ):
        assessment["missing_fields"] = [
            path
            for path in assessment["missing_fields"]
            if path not in changed_nonnull_paths
        ]
    version = ClientProfileVersion(
        client_profile_id=profile_id,
        version_number=next_client_profile_version(db, profile_id),
        status=base.status,
        data=data,
    )
    db.add(version)
    db.flush()
    return version


def reject_review_draft(
    db: Session, profile_id: uuid.UUID, version_id: uuid.UUID, body: ReviewRejectIn
) -> ClientProfileVersion:
    """Mark the open draft rejected with its reason. Caller owns commit/rollback.

    Rejection never creates a version and never sets approval metadata, so the
    latest approved profile stays whatever it was before.
    """
    draft = _lock_editable_head(db, profile_id, version_id)
    draft.status = ReviewStatus.REJECTED
    draft.rejection_reason = body.reason
    draft.rejected_at = datetime.now(timezone.utc)
    db.flush()
    return draft
