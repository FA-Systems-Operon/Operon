import uuid

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from src.audit import record_audit_event
from src.models import AuditEvent, Role, User


@pytest.fixture
def actor(db_session):
    user = User(
        email=f"{uuid.uuid4()}@example.test",
        display_name="Audit test user",
        password_hash="unused",
        role=Role.REVIEWER,
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_audit_event_records_attribution_and_version(db_session, actor):
    object_id, version_id = uuid.uuid4(), uuid.uuid4()
    event = record_audit_event(
        db_session,
        actor_id=actor.id,
        action="edit",
        object_type="client_profile",
        object_id=object_id,
        version_id=version_id,
    )
    db_session.commit()
    db_session.refresh(event)
    assert event.actor_id == actor.id
    assert event.action == "edit"
    assert event.object_type == "client_profile"
    assert event.object_id == object_id
    assert event.version_id == version_id
    assert event.created_at.tzinfo is not None


def test_audit_event_rolls_back_with_action(db_session, actor):
    actor.display_name = "Changed"
    event = record_audit_event(
        db_session,
        actor_id=actor.id,
        action="edit",
        object_type="user",
        object_id=actor.id,
    )
    db_session.flush()
    actor_id, event_id = actor.id, event.id
    db_session.rollback()
    assert db_session.get(User, actor_id) is None
    assert db_session.get(AuditEvent, event_id) is None


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_audit_events_are_append_only(db_session, actor, operation):
    event = record_audit_event(
        db_session,
        actor_id=actor.id,
        action="upload",
        object_type="source_document",
        object_id=uuid.uuid4(),
    )
    db_session.commit()
    event_id = event.id
    statement = (
        update(AuditEvent).values(action="edit")
        if operation == "update"
        else delete(AuditEvent)
    )
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(statement.where(AuditEvent.id == event_id))
    db_session.rollback()
    assert db_session.get(AuditEvent, event_id).action == "upload"
