"""Review inbox: latest profile drafts awaiting review (#54)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.models import ClientProfileVersion, JobStatus, ReviewStatus

INBOX = "/api/v1/reviews"
DRAFT = {"name": "Maya Chen", "needs": ["More bookings"], "source_references": []}


@pytest.fixture
def add_version(db_session):
    """Save a non-empty version of the given profile, like a generated draft."""

    def add(profile_id, number, *, status=ReviewStatus.DRAFT, created_at=None):
        version = ClientProfileVersion(
            client_profile_id=profile_id,
            version_number=number,
            data=DRAFT,
            status=status,
            created_at=created_at,
        )
        db_session.add(version)
        db_session.commit()
        return version

    return add


@pytest.mark.parametrize("status", [ReviewStatus.DRAFT, ReviewStatus.IN_REVIEW])
def test_generated_draft_appears_with_client_and_time(
    client, db_session, demo_client, profile_factory, add_version, make_pair, status
):
    placeholder = profile_factory()
    draft = add_version(placeholder.client_profile_id, 2, status=status)
    job = make_pair(status=JobStatus.SUCCEEDED)
    job.result_version_id = draft.id
    db_session.commit()

    response = client.get(INBOX)

    assert response.status_code == 200
    [item] = response.json()
    assert datetime.fromisoformat(item.pop("created_at")) == draft.created_at
    assert item == {
        "version_id": str(draft.id),
        "client_profile_id": str(draft.client_profile_id),
        "version_number": 2,
        "client_id": str(demo_client.id),
        "client_name": "Demo Client",
        "status": status.value,
    }


def test_empty_placeholder_is_not_listed(client, demo_client):
    created = client.post("/client-profiles", params={"client_id": str(demo_client.id)})
    assert created.status_code == 201
    assert created.json()["status"] == "draft"

    assert client.get(INBOX).json() == []


@pytest.mark.parametrize(
    "status", [ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.STALE]
)
def test_reviewed_versions_are_not_listed(client, profile_factory, add_version, status):
    placeholder = profile_factory()
    add_version(placeholder.client_profile_id, 2, status=status)

    assert client.get(INBOX).json() == []


def test_only_the_latest_version_of_each_profile_is_listed(
    client, profile_factory, add_version
):
    first = profile_factory()
    add_version(first.client_profile_id, 2)
    latest = add_version(first.client_profile_id, 3)
    # An older draft whose newer version is already approved awaits nothing.
    second = profile_factory()
    add_version(second.client_profile_id, 2)
    add_version(second.client_profile_id, 3, status=ReviewStatus.APPROVED)

    items = client.get(INBOX).json()

    assert [item["version_id"] for item in items] == [str(latest.id)]


def test_a_correction_to_a_job_draft_replaces_it(
    client, db_session, profile_factory, add_version, make_pair
):
    placeholder = profile_factory()
    job_draft = add_version(placeholder.client_profile_id, 2)
    job = make_pair(status=JobStatus.SUCCEEDED)
    job.result_version_id = job_draft.id
    db_session.commit()

    corrected = client.put(
        f"/client-profiles/{placeholder.client_profile_id}",
        json={**DRAFT, "name": "Maya Chen-Lee"},
    )
    assert corrected.status_code == 200

    items = client.get(INBOX).json()
    assert [item["version_id"] for item in items] == [corrected.json()["id"]]
    assert items[0]["version_number"] == 3


def test_multiple_clients_are_named_and_newest_first(
    client, client_factory, profile_factory, add_version
):
    now = datetime.now(timezone.utc)
    for name, hours_ago in [("Bakery", 3), ("Florist", 1), ("Garage", 2)]:
        placeholder = profile_factory(client_factory(name))
        add_version(
            placeholder.client_profile_id,
            2,
            created_at=now - timedelta(hours=hours_ago),
        )

    items = client.get(INBOX).json()

    assert [item["client_name"] for item in items] == ["Florist", "Garage", "Bakery"]


def test_no_drafts_returns_an_empty_list(client):
    response = client.get(INBOX)

    assert response.status_code == 200
    assert response.json() == []
