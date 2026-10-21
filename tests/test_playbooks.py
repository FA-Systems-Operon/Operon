"""Tests for the playbook endpoints."""

import uuid

# --- POST /playbooks ---


def test_create_playbook(client):
    response = client.post("/playbooks")

    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 1
    assert body["data"] == {}
    assert body["status"] == "draft"
    assert body["approved_at"] is None
    assert body["approved_by"] is None
    assert "id" in body
    assert "playbook_id" in body
    assert "created_at" in body


# --- PUT /playbooks/{id} ---


def test_update_playbook_creates_new_version(client):
    create = client.post("/playbooks")
    playbook_id = create.json()["playbook_id"]

    update = client.put(f"/playbooks/{playbook_id}", json={"step": "one"})

    assert update.status_code == 200
    assert update.json()["version_number"] == 2
    assert update.json()["data"] == {"step": "one"}


def test_update_playbook_increments_version_each_time(client):
    create = client.post("/playbooks")
    playbook_id = create.json()["playbook_id"]

    client.put(f"/playbooks/{playbook_id}", json={})
    third = client.put(f"/playbooks/{playbook_id}", json={})

    assert third.json()["version_number"] == 3


def test_update_unknown_playbook_returns_404(client):
    response = client.put(f"/playbooks/{uuid.uuid4()}", json={})

    assert response.status_code == 404


def test_update_does_not_inherit_approval_or_touch_old_version(
    client, playbook_factory
):
    """Editing an approved playbook is a NEW unapproved version; v1 is untouched."""
    v1 = playbook_factory(approved=True, data={"rule": "original"})

    update = client.put(f"/playbooks/{v1.playbook_id}", json={"rule": "changed"})

    new = update.json()
    assert new["status"] == "draft"
    assert new["approved_at"] is None
    assert new["approved_by"] is None

    versions = client.get(f"/playbooks/{v1.playbook_id}/versions").json()
    assert versions[0]["status"] == "approved"
    assert versions[0]["approved_at"] is not None
    assert versions[0]["data"] == {"rule": "original"}  # not overwritten
    assert versions[1]["data"] == {"rule": "changed"}


# --- GET /playbooks/{id}/versions ---


def test_list_playbook_versions_oldest_first(client):
    create = client.post("/playbooks")
    playbook_id = create.json()["playbook_id"]
    client.put(f"/playbooks/{playbook_id}", json={"v": 2})
    client.put(f"/playbooks/{playbook_id}", json={"v": 3})

    response = client.get(f"/playbooks/{playbook_id}/versions")

    assert response.status_code == 200
    versions = response.json()
    assert len(versions) == 3
    assert [v["version_number"] for v in versions] == [1, 2, 3]


def test_list_versions_unknown_playbook_returns_404(client):
    response = client.get(f"/playbooks/{uuid.uuid4()}/versions")

    assert response.status_code == 404


# --- POST /playbooks/{id}/versions/{version_id}/approve ---


def test_approve_playbook_version(api, playbook_factory):
    v1 = playbook_factory()

    response = api.approve_playbook(v1.playbook_id, v1.id)

    assert response.status_code == 200
    body = response.json()
    assert body["version"]["id"] == str(v1.id)
    assert body["version"]["status"] == "approved"
    assert body["version"]["approved_by"] == api.reviewer
    assert body["version"]["approved_at"] is not None
    assert body["newly_stale_artifact_version_ids"] == []


def test_approve_already_approved_version_returns_409(api, playbook_factory):
    v1 = playbook_factory(approved=True)

    response = api.approve_playbook(v1.playbook_id, v1.id)

    assert response.status_code == 409


def test_approve_unknown_version_returns_404(api, playbook_factory):
    v1 = playbook_factory()

    response = api.approve_playbook(v1.playbook_id, uuid.uuid4())

    assert response.status_code == 404


def test_approve_unknown_playbook_returns_404(api, playbook_factory):
    v1 = playbook_factory()

    response = api.approve_playbook(uuid.uuid4(), v1.id)

    assert response.status_code == 404


def test_approve_version_of_a_different_playbook_returns_404(api, playbook_factory):
    """Right version id under the wrong playbook id must not approve anything."""
    v1 = playbook_factory()
    other = playbook_factory()

    response = api.approve_playbook(v1.playbook_id, other.id)

    assert response.status_code == 404


def test_approve_requires_approved_by(client, playbook_factory):
    v1 = playbook_factory()

    response = client.post(
        f"/playbooks/{v1.playbook_id}/versions/{v1.id}/approve", json={}
    )

    assert response.status_code == 422


# --- GET /playbooks/{id}/latest-approved ---


def test_latest_approved_unknown_playbook_returns_404(client):
    response = client.get(f"/playbooks/{uuid.uuid4()}/latest-approved")

    assert response.status_code == 404


def test_latest_approved_without_any_approval_returns_404(client, playbook_factory):
    v1 = playbook_factory()

    response = client.get(f"/playbooks/{v1.playbook_id}/latest-approved")

    assert response.status_code == 404
    assert response.json()["detail"] == "No approved version found"


def test_latest_approved_returns_the_approved_version(client, playbook_factory):
    v1 = playbook_factory(approved=True)

    response = client.get(f"/playbooks/{v1.playbook_id}/latest-approved")

    assert response.status_code == 200
    assert response.json()["id"] == str(v1.id)


def test_latest_approved_ignores_newer_unapproved_drafts(client, playbook_factory):
    v1 = playbook_factory(approved=True)
    client.put(f"/playbooks/{v1.playbook_id}", json={"draft": True})

    response = client.get(f"/playbooks/{v1.playbook_id}/latest-approved")

    assert response.json()["id"] == str(v1.id)


def test_latest_approved_is_highest_version_not_latest_approval(
    client, api, playbook_factory
):
    """Approving an older version later must not roll the current record back."""
    v1 = playbook_factory()
    pid = v1.playbook_id
    v2 = client.put(f"/playbooks/{pid}", json={"n": 2}).json()
    v3 = client.put(f"/playbooks/{pid}", json={"n": 3}).json()

    api.approve_playbook(pid, v3["id"])
    api.approve_playbook(pid, v2["id"])  # approved afterwards, but older

    response = client.get(f"/playbooks/{pid}/latest-approved")

    assert response.json()["id"] == v3["id"]
