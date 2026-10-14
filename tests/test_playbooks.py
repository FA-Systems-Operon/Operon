"""Tests for the playbook endpoints."""

import uuid


# --- POST /playbooks ---


def test_create_playbook(client):
    response = client.post("/playbooks")

    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 1
    assert body["data"] == {}
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
