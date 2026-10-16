"""Tests for the client profile endpoints."""

import uuid

# --- POST /client-profiles ---


def test_create_client_profile(client, demo_client):
    response = client.post(
        "/client-profiles", params={"client_id": str(demo_client.id)}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 1
    assert body["data"] == {}
    assert "id" in body
    assert "client_profile_id" in body
    assert "created_at" in body


# --- PUT /client-profiles/{id} ---


def test_update_client_profile_creates_new_version(client, demo_client):
    create = client.post("/client-profiles", params={"client_id": str(demo_client.id)})
    profile_id = create.json()["client_profile_id"]

    update = client.put(f"/client-profiles/{profile_id}", json={"key": "value"})

    assert update.status_code == 200
    assert update.json()["version_number"] == 2
    assert update.json()["data"] == {"key": "value"}


def test_update_client_profile_increments_version_each_time(client, demo_client):
    create = client.post("/client-profiles", params={"client_id": str(demo_client.id)})
    profile_id = create.json()["client_profile_id"]

    client.put(f"/client-profiles/{profile_id}", json={})
    third = client.put(f"/client-profiles/{profile_id}", json={})

    assert third.json()["version_number"] == 3


def test_update_unknown_client_profile_returns_404(client):
    response = client.put(f"/client-profiles/{uuid.uuid4()}", json={})

    assert response.status_code == 404


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
