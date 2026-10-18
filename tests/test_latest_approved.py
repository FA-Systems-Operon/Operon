"""Approved retrieval against real PostgreSQL, for both versioned record types."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.models import ClientProfile, ClientProfileVersion, Playbook, PlaybookVersion
from src.versioning import (
    get_latest_approved_client_profile_version,
    get_latest_approved_playbook_version,
)

APPROVAL_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(params=["profile", "playbook"])
def record_type(request, db_session, demo_client):
    if request.param == "profile":
        return SimpleNamespace(
            parent=ClientProfile,
            model=ClientProfileVersion,
            foreign_key="client_profile_id",
            path="/client-profiles",
            create_params={"client_id": str(demo_client.id)},
            parent_fields={"client_id": demo_client.id},
            retrieve=get_latest_approved_client_profile_version,
            missing_detail="Client profile not found",
        )
    return SimpleNamespace(
        parent=Playbook,
        model=PlaybookVersion,
        foreign_key="playbook_id",
        path="/playbooks",
        create_params={},
        parent_fields={},
        retrieve=get_latest_approved_playbook_version,
        missing_detail="Playbook not found",
    )


@pytest.fixture
def record_factory(record_type, db_session):
    def create():
        record = record_type.parent(**record_type.parent_fields)
        db_session.add(record)
        db_session.commit()
        return record

    return create


@pytest.fixture
def version_factory(record_type, db_session):
    def create(record, number, approved_at=None, **kwargs):
        version = record_type.model(
            **{record_type.foreign_key: record.id},
            version_number=number,
            data={"service_area": f"Area {number}"},
            approved_at=approved_at,
            **kwargs,
        )
        db_session.add(version)
        db_session.commit()
        return version

    return create


def test_highest_approved_version_wins_over_approval_and_creation_time(
    record_type, record_factory, version_factory, db_session, client
):
    record = record_factory()
    # Deliberately insert out of order: neither insertion time, creation time,
    # nor most recent approval should decide which version is current.
    expected = version_factory(record, 3, APPROVAL_TIME, created_at=APPROVAL_TIME)
    version_factory(
        record,
        2,
        APPROVAL_TIME + timedelta(days=1),
        created_at=APPROVAL_TIME + timedelta(days=1),
    )
    version_factory(record, 4)  # A newer draft must not be returned.
    version_factory(record, 1, APPROVAL_TIME + timedelta(days=2))

    assert record_type.retrieve(db_session, record.id).id == expected.id
    response = client.get(f"{record_type.path}/{record.id}/latest-approved")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(expected.id)
    assert body["version_number"] == 3
    assert body["data"] == expected.data
    assert body[record_type.foreign_key] == str(record.id)
    assert datetime.fromisoformat(body["approved_at"]) == APPROVAL_TIME


@pytest.mark.parametrize("with_draft", [False, True])
def test_no_approved_version_has_no_fallback(
    record_type, record_factory, version_factory, db_session, client, with_draft
):
    record = record_factory()
    if with_draft:
        version_factory(record, 1)
    assert record_type.retrieve(db_session, record.id) is None
    response = client.get(f"{record_type.path}/{record.id}/latest-approved")
    assert response.status_code == 404
    assert response.json() == {"detail": "No approved version found"}


def test_unknown_record_returns_404(record_type, db_session, client):
    record_id = uuid.uuid4()
    assert record_type.retrieve(db_session, record_id) is None
    response = client.get(f"{record_type.path}/{record_id}/latest-approved")
    assert response.status_code == 404
    assert response.json() == {"detail": record_type.missing_detail}


def test_invalid_record_id_returns_422(record_type, client):
    response = client.get(f"{record_type.path}/not-a-uuid/latest-approved")
    assert response.status_code == 422


def test_other_records_approved_versions_are_excluded(
    record_type, record_factory, version_factory, db_session, client
):
    record, other = record_factory(), record_factory()
    version_factory(record, 1)
    version_factory(other, 99, APPROVAL_TIME)
    assert record_type.retrieve(db_session, record.id) is None
    assert (
        client.get(f"{record_type.path}/{record.id}/latest-approved").status_code == 404
    )

    expected = version_factory(record, 2, APPROVAL_TIME)
    assert record_type.retrieve(db_session, record.id).id == expected.id
    response = client.get(f"{record_type.path}/{record.id}/latest-approved")
    assert response.json()["id"] == str(expected.id)


def test_approval_of_a_newer_version_changes_the_result(
    record_type, record_factory, version_factory, db_session, client
):
    record = record_factory()
    old = version_factory(record, 1, APPROVAL_TIME)
    new = version_factory(record, 2)
    url = f"{record_type.path}/{record.id}/latest-approved"
    assert client.get(url).json()["id"] == str(old.id)
    # Fixture-level approval: this feature does not expose an approval action.
    new.approved_at = APPROVAL_TIME + timedelta(days=1)
    db_session.commit()
    assert client.get(url).json()["id"] == str(new.id)


def test_new_records_and_edits_are_unapproved_and_preserve_approved_history(
    record_type, db_session, client
):
    created = client.post(record_type.path, params=record_type.create_params)
    assert created.status_code == 201
    first = created.json()
    assert first["approved_at"] is None
    record_id = first[record_type.foreign_key]
    old = db_session.get(record_type.model, uuid.UUID(first["id"]))
    old.approved_at = APPROVAL_TIME
    db_session.commit()

    # Even a data key called approved_at must not set approval metadata.
    update = client.put(
        f"{record_type.path}/{record_id}",
        json={"service_area": "New area", "approved_at": APPROVAL_TIME.isoformat()},
    )
    assert update.status_code == 200
    assert update.json()["version_number"] == 2
    assert update.json()["approved_at"] is None
    db_session.expire_all()
    assert old.data == first["data"]
    assert old.approved_at == APPROVAL_TIME
    response = client.get(f"{record_type.path}/{record_id}/latest-approved")
    assert response.json()["id"] == first["id"]
    history = client.get(f"{record_type.path}/{record_id}/versions").json()
    assert history[0]["approved_at"] is not None
    assert history[1]["approved_at"] is None


