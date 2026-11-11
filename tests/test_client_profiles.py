"""Tests for the client profile endpoints."""

import uuid

from sqlalchemy import select

from src.models import AuditEvent

# --- POST /client-profiles ---


def test_create_client_profile(client, demo_client):
    response = client.post(
        "/client-profiles", params={"client_id": str(demo_client.id)}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 1
    assert body["data"] == {}
    assert body["status"] == "draft"
    assert body["approved_at"] is None
    assert body["approved_by"] is None
    assert "id" in body
    assert "client_profile_id" in body
    assert "created_at" in body


# --- PUT /client-profiles/{id} ---


def test_update_client_profile_creates_new_version(
    client, db_session, demo_client, signed_in_user
):
    create = client.post("/client-profiles", params={"client_id": str(demo_client.id)})
    profile_id = create.json()["client_profile_id"]

    update = client.put(f"/client-profiles/{profile_id}", json={"key": "value"})

    assert update.status_code == 200
    assert update.json()["version_number"] == 2
    assert update.json()["data"] == {"key": "value"}
    events = {
        event.action: event
        for event in db_session.scalars(
            select(AuditEvent).where(AuditEvent.object_id == uuid.UUID(profile_id))
        )
    }
    assert set(events) == {"draft_created", "edit"}
    assert events["draft_created"].version_id == uuid.UUID(create.json()["id"])
    assert events["edit"].version_id == uuid.UUID(update.json()["id"])
    assert events["edit"].actor_id == signed_in_user.id


def test_update_client_profile_increments_version_each_time(client, demo_client):
    create = client.post("/client-profiles", params={"client_id": str(demo_client.id)})
    profile_id = create.json()["client_profile_id"]

    client.put(f"/client-profiles/{profile_id}", json={})
    third = client.put(f"/client-profiles/{profile_id}", json={})

    assert third.json()["version_number"] == 3


def test_update_unknown_client_profile_returns_404(client):
    response = client.put(f"/client-profiles/{uuid.uuid4()}", json={})

    assert response.status_code == 404


def test_update_does_not_inherit_approval_or_touch_old_version(
    client, profile_factory, sample_profile
):
    """A correction to an approved profile is a NEW unapproved version; v1 is untouched."""
    v1 = profile_factory(approved=True, data={"budget": 1000})

    update = client.put(f"/client-profiles/{v1.client_profile_id}", json=sample_profile)

    new = update.json()
    assert new["status"] == "draft"
    assert new["approved_at"] is None
    assert new["approved_by"] is None

    versions = client.get(f"/client-profiles/{v1.client_profile_id}/versions").json()
    assert versions[0]["status"] == "approved"
    assert versions[0]["approved_at"] is not None
    assert versions[0]["data"] == {"budget": 1000}  # not overwritten
    assert versions[1]["data"] == sample_profile


# --- GET /client-profiles/{id}/versions ---


def test_list_client_profile_versions_oldest_first(client, demo_client):
    create = client.post("/client-profiles", params={"client_id": str(demo_client.id)})
    profile_id = create.json()["client_profile_id"]
    client.put(f"/client-profiles/{profile_id}", json={"v": 2})
    client.put(f"/client-profiles/{profile_id}", json={"v": 3})

    response = client.get(f"/client-profiles/{profile_id}/versions")

    assert response.status_code == 200
    versions = response.json()
    assert len(versions) == 3
    assert [v["version_number"] for v in versions] == [1, 2, 3]


def test_list_versions_unknown_client_profile_returns_404(client):
    response = client.get(f"/client-profiles/{uuid.uuid4()}/versions")

    assert response.status_code == 404


# --- POST /client-profiles/{id}/versions/{version_id}/approve ---


def test_approve_client_profile_version(api, profile_factory):
    v1 = profile_factory()

    response = api.approve_profile(v1.client_profile_id, v1.id)

    assert response.status_code == 200
    body = response.json()
    assert body["version"]["id"] == str(v1.id)
    assert body["version"]["status"] == "approved"
    assert body["version"]["approved_by"] == api.reviewer
    assert body["version"]["approved_at"] is not None
    assert body["newly_stale_artifact_version_ids"] == []  # nothing depended on it


def test_approve_already_approved_version_returns_409(api, db_session, profile_factory):
    v1 = profile_factory(approved=True)

    response = api.approve_profile(v1.client_profile_id, v1.id)

    assert response.status_code == 409
    assert db_session.scalars(select(AuditEvent)).first() is None


def test_approve_unknown_version_returns_404(api, profile_factory):
    v1 = profile_factory()

    response = api.approve_profile(v1.client_profile_id, uuid.uuid4())

    assert response.status_code == 404


def test_approve_unknown_profile_returns_404(api, profile_factory):
    v1 = profile_factory()

    response = api.approve_profile(uuid.uuid4(), v1.id)

    assert response.status_code == 404


def test_approve_version_of_a_different_profile_returns_404(
    api, profile_factory, client_factory
):
    """Right version id under the wrong profile id must not approve anything."""
    v1 = profile_factory()
    other = profile_factory(client_factory("Other"))

    response = api.approve_profile(v1.client_profile_id, other.id)

    assert response.status_code == 404


def test_approval_audit_uses_session_actor(
    client, db_session, profile_factory, signed_in_user
):
    version = profile_factory()
    response = client.post(
        f"/client-profiles/{version.client_profile_id}/versions/{version.id}/approve",
        json={"approved_by": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["version"]["approved_by"] == str(signed_in_user.id)
    audit = db_session.scalars(select(AuditEvent)).one()
    assert audit.actor_id == signed_in_user.id
    assert audit.action == "approve"
    assert audit.object_id == version.client_profile_id
    assert audit.version_id == version.id


# --- GET /client-profiles/{id}/latest-approved ---


def test_latest_approved_unknown_profile_returns_404(client):
    response = client.get(f"/client-profiles/{uuid.uuid4()}/latest-approved")

    assert response.status_code == 404


def test_latest_approved_without_any_approval_returns_404(client, profile_factory):
    v1 = profile_factory()

    response = client.get(f"/client-profiles/{v1.client_profile_id}/latest-approved")

    assert response.status_code == 404
    assert response.json()["detail"] == "No approved version found"


def test_latest_approved_returns_the_approved_version(client, profile_factory):
    v1 = profile_factory(approved=True)

    response = client.get(f"/client-profiles/{v1.client_profile_id}/latest-approved")

    assert response.status_code == 200
    assert response.json()["id"] == str(v1.id)


def test_latest_approved_ignores_newer_unapproved_drafts(client, profile_factory):
    v1 = profile_factory(approved=True)
    client.put(f"/client-profiles/{v1.client_profile_id}", json={"draft": True})

    response = client.get(f"/client-profiles/{v1.client_profile_id}/latest-approved")

    assert response.json()["id"] == str(v1.id)


def test_latest_approved_is_highest_version_not_latest_approval(
    client, api, profile_factory
):
    """Approving an older version later must not roll the current record back."""
    v1 = profile_factory()
    pid = v1.client_profile_id
    v2 = client.put(f"/client-profiles/{pid}", json={"n": 2}).json()
    v3 = client.put(f"/client-profiles/{pid}", json={"n": 3}).json()

    api.approve_profile(pid, v3["id"])
    api.approve_profile(pid, v2["id"])

    response = client.get(f"/client-profiles/{pid}/latest-approved")

    assert response.json()["id"] == v3["id"]
