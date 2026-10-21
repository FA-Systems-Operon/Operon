from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from src.config import settings
from src.main import app, check_db, check_ollama

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_reports_db_and_ollama():
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    body = response.json()
    assert body["api"] == "ok"
    assert "db" in body
    assert "ollama" in body
    assert "status" in body["ollama"]


def test_ollama_test_requires_model(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MODEL", "")
    response = client.get("/api/v1/ollama/test")
    assert response.status_code == 503


def test_check_db_ok():
    assert check_db() == "ok"


def test_check_db_error():
    with patch("src.main.engine") as engine:
        engine.connect.side_effect = SQLAlchemyError("unavailable")
        assert check_db().startswith("error:")


@pytest.fixture
def fake_ollama(monkeypatch):
    """Route the adapter's HTTP calls to a handler instead of a real Ollama."""

    def install(handler, *, model="llama3"):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        monkeypatch.setattr("src.ai.ollama._default_client", client)
        monkeypatch.setattr(settings, "AI_PROVIDER", "ollama")
        monkeypatch.setattr(settings, "OLLAMA_MODEL", model)

    return install


def test_check_ollama_ok(fake_ollama):
    fake_ollama(
        lambda request: httpx.Response(200, json={"models": [{"name": "llama3"}]})
    )
    info = check_ollama()
    assert info["status"] == "ok"
    assert info["models"] == ["llama3"]
    assert info["model_installed"] is True


def test_check_ollama_works_without_model(fake_ollama):
    fake_ollama(
        lambda request: httpx.Response(200, json={"models": [{"name": "llama3"}]}),
        model="",
    )
    info = check_ollama()
    assert info["status"] == "ok"
    assert info["model_installed"] is False


def test_check_ollama_http_error(fake_ollama):
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    fake_ollama(handler)
    info = check_ollama()
    assert info["status"].startswith("error:")


def test_ollama_test_success(fake_ollama):
    fake_ollama(lambda request: httpx.Response(200, json={"response": "hello there"}))
    response = client.get("/api/v1/ollama/test")
    assert response.status_code == 200
    assert response.json() == {"model": "llama3", "response": "hello there"}


def test_ollama_test_http_status_error(fake_ollama):
    fake_ollama(lambda request: httpx.Response(404, text="model not found"))
    response = client.get("/api/v1/ollama/test")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["ollama_status"] == 404
    assert detail["ollama_body"] == "model not found"


def test_ollama_test_http_error(fake_ollama):
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    fake_ollama(handler)
    response = client.get("/api/v1/ollama/test")
    assert response.status_code == 503
