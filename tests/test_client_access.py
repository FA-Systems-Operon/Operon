"""Database constraints for explicit user-to-client assignments (#148)."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import IntegrityError

from src.models import Client, ClientAccess, Role, User


def test_stores_multiple_assignments_with_timestamps(
    db_session, signed_in_user, demo_client
):
    other_user = User(
        email="other@example.test",
        display_name="Other reviewer",
        password_hash="unused",
        role=Role.REVIEWER,
    )
    other_client = Client(name="Other client")
    db_session.add_all([other_user, other_client])
    db_session.flush()
    pairs = [
        (signed_in_user.id, demo_client.id),
        (signed_in_user.id, other_client.id),
        (other_user.id, demo_client.id),
    ]
    db_session.add_all(
        ClientAccess(user_id=user_id, client_id=client_id)
        for user_id, client_id in pairs
    )
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.scalars(select(ClientAccess)).all()
    assert {(item.user_id, item.client_id) for item in stored} == set(pairs)
    assert all(item.created_at.tzinfo is not None for item in stored)


def test_duplicate_assignment_preserves_original(
    db_session, signed_in_user, demo_client
):
    values = {"user_id": signed_in_user.id, "client_id": demo_client.id}
    db_session.execute(insert(ClientAccess).values(**values))
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(insert(ClientAccess).values(**values))
    db_session.rollback()

    assert len(db_session.scalars(select(ClientAccess)).all()) == 1


@pytest.mark.parametrize("missing", ["user_id", "client_id"])
def test_assignment_requires_existing_records(
    db_session, signed_in_user, demo_client, missing
):
    values = {"user_id": signed_in_user.id, "client_id": demo_client.id}
    values[missing] = uuid.uuid4()

    with pytest.raises(IntegrityError):
        db_session.execute(insert(ClientAccess).values(**values))
    db_session.rollback()

    assert db_session.scalars(select(ClientAccess)).all() == []


@pytest.mark.parametrize("removed_model", [User, Client])
def test_deleting_record_removes_only_its_assignments(
    db_session, signed_in_user, demo_client, removed_model
):
    db_session.add(ClientAccess(user_id=signed_in_user.id, client_id=demo_client.id))
    db_session.commit()
    record_id = signed_in_user.id if removed_model is User else demo_client.id
    db_session.execute(delete(removed_model).where(removed_model.id == record_id))
    db_session.commit()

    assert db_session.scalars(select(ClientAccess)).all() == []
    remaining_model = Client if removed_model is User else User
    assert db_session.scalars(select(remaining_model)).one() is not None


def test_migration_can_be_reapplied_without_losing_assignments(
    db_session, signed_in_user, demo_client
):
    migration = (
        Path(__file__).resolve().parents[1]
        / "backend/migrations/011_add_client_access.sql"
    ).read_text()
    # Recreate only the new table to exercise upgrading an existing database.
    db_session.execute(text("DROP TABLE client_access"))
    db_session.execute(text(migration))
    db_session.execute(
        insert(ClientAccess).values(user_id=signed_in_user.id, client_id=demo_client.id)
    )
    db_session.execute(text(migration))
    db_session.commit()

    stored = db_session.scalars(select(ClientAccess)).one()
    assert stored.user_id == signed_in_user.id
    assert stored.client_id == demo_client.id
    assert stored.created_at.tzinfo is not None
