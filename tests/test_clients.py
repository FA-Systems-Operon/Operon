"""Tests for the client endpoints: create and lookup."""

import uuid


# --- POST /clients ---


def test_create_client(client):
    response = client.post("/clients", json={"name": "ABC Corp"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "ABC Corp"
    assert "id" in body
    assert "created_at" in body


def test_create_client_missing_name(client):
    response = client.post("/clients", json={})

    """Unprocessable Content (Semantic Error)"""
    assert response.status_code == 422 


def test_create_client_empty_name(client):
    response = client.post("/clients", json={"name": ""})

    assert response.status_code == 422


# --- GET /clients/{client_id} ---

"""Demo client is created in the demo_client fixture, so we can use it in tests without having to create it in each test."""
def test_get_client(client, demo_client): 
    response = client.get(f"/clients/{demo_client.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(demo_client.id)
    assert body["name"] == demo_client.name


def test_get_unknown_client_returns_404(client):
    response = client.get(f"/clients/{uuid.uuid4()}")

    assert response.status_code == 404
