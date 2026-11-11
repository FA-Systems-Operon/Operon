"""Write audit events in the transaction that performs the action."""

import uuid

from sqlalchemy.orm import Session

from src.models import AuditEvent


def record_audit_event(
    db: Session,
    *,
    actor_id: uuid.UUID,
    action: str,
    object_type: str,
    object_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Stage an event. The caller commits or rolls back the action and event together."""
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        version_id=version_id,
    )
    db.add(event)
    return event
