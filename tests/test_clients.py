"""Tests for the client endpoints: create, list and lookup."""

import uuid

CLIENTS_URL = "/api/v1/clients"

# --- POST /api/v1/clients ---


def test_create_client(client):
    response = client.post(CLIENTS_URL, json={"name": "ABC Corp"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "ABC Corp"
    assert "id" in body
    assert "created_at" in body


def test_create_client_missing_name(client):
    response = client.post(CLIENTS_URL, json={})

    """Unprocessable Content (Semantic Error)"""
    assert response.status_code == 422


def test_create_client_empty_name(client):
    response = client.post(CLIENTS_URL, json={"name": ""})

    assert response.status_code == 422


# --- GET /api/v1/clients ---


def test_list_clients_empty(client):
    response = client.get(CLIENTS_URL)

    assert response.status_code == 200
    assert response.json() == []


def test_list_clients_sorted_by_name(client, client_factory):
    zeta = client_factory("Zeta Dental")
    acme = client_factory("Acme Plumbing")

    response = client.get(CLIENTS_URL)

    assert response.status_code == 200
    assert [(c["id"], c["name"]) for c in response.json()] == [
        (str(acme.id), "Acme Plumbing"),
        (str(zeta.id), "Zeta Dental"),
    ]


def test_old_unprefixed_clients_path_is_gone(client):
    # Everything the frontend calls lives under /api/v1, which the proxy forwards.
    assert client.get("/clients").status_code == 404


# --- GET /api/v1/clients/{client_id} ---

"""Demo client is created in the demo_client fixture, so we can use it in tests without having to create it in each test."""


def test_get_client(client, demo_client):
    response = client.get(f"{CLIENTS_URL}/{demo_client.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(demo_client.id)
    assert body["name"] == demo_client.name


def test_get_unknown_client_returns_404(client):
    response = client.get(f"{CLIENTS_URL}/{uuid.uuid4()}")

    assert response.status_code == 404
