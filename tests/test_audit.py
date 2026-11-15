import uuid

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError

from src.audit import AuditAction, record_audit_event
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
        action=AuditAction.EDIT,
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
        action=AuditAction.EDIT,
        object_type="user",
        object_id=actor.id,
    )
    db_session.flush()
    actor_id, event_id = actor.id, event.id
    db_session.rollback()
    assert db_session.get(User, actor_id) is None
    assert db_session.get(AuditEvent, event_id) is None


@pytest.mark.parametrize("operation", ["update", "delete", "truncate"])
def test_audit_events_are_append_only(db_session, actor, operation):
    event = record_audit_event(
        db_session,
        actor_id=actor.id,
        action=AuditAction.UPLOAD,
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
    statement = (
        text("TRUNCATE audit_events")
        if operation == "truncate"
        else statement.where(AuditEvent.id == event_id)
    )
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.execute(statement)
    db_session.rollback()
    assert db_session.get(AuditEvent, event_id).action == "upload"


def test_audit_event_rejects_unknown_action(db_session, actor):
    with pytest.raises(ValueError, match="not a valid AuditAction"):
        record_audit_event(
            db_session,
            actor_id=actor.id,
            action="uplod",
            object_type="source_document",
            object_id=uuid.uuid4(),
        )
