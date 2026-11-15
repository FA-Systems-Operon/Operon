"""Write audit events in the transaction that performs the action."""

import uuid
from enum import StrEnum

from sqlalchemy.orm import Session

from src.models import AuditEvent


class AuditAction(StrEnum):
    UPLOAD = "upload"
    JOB_STARTED = "job_started"
    JOB_REQUEUED = "job_requeued"
    DRAFT_CREATED = "draft_created"
    EDIT = "edit"
    APPROVE = "approve"
    REJECT = "reject"


def record_audit_event(
    db: Session,
    *,
    actor_id: uuid.UUID,
    action: AuditAction,
    object_type: str,
    object_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Stage an event. The caller commits or rolls back the action and event together."""
    event = AuditEvent(
        actor_id=actor_id,
        action=AuditAction(action).value,
        object_type=object_type,
        object_id=object_id,
        version_id=version_id,
    )
    db.add(event)
    return event
