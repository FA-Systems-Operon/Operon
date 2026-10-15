from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

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


def test_ollama_test_requires_model():
    response = client.get("/api/v1/ollama/test")
    assert response.status_code == 503


def test_check_db_ok():
    assert check_db() == "ok"


def test_check_db_error():
    with patch("src.main.engine") as engine:
        engine.connect.side_effect = SQLAlchemyError("unavailable")
        assert check_db().startswith("error:")


def test_check_ollama_ok():
    payload = {"models": [{"name": "llama3"}]}
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = payload
    with (
        patch("src.main.httpx.get", return_value=mock_response),
        patch("src.main.OLLAMA_MODEL", "llama3"),
    ):
        info = check_ollama()
    assert info["status"] == "ok"
    assert info["model_installed"] is True


def test_check_ollama_http_error():
    with patch(
        "src.main.httpx.get",
        side_effect=httpx.ConnectError("offline"),
    ):
        info = check_ollama()
    assert info["status"].startswith("error:")


def test_ollama_test_success():
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json.return_value = {"response": "hello there"}
    with (
        patch("src.main.OLLAMA_MODEL", "llama3"),
        patch("src.main.httpx.post", return_value=mock_response),
    ):
        response = client.get("/api/v1/ollama/test")
    assert response.status_code == 200
    assert response.json()["response"] == "hello there"


def test_ollama_test_http_status_error():
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.text = "model not found"
    error = httpx.HTTPStatusError(
        "rejected",
        request=Mock(),
        response=mock_response,
    )
    with (
        patch("src.main.OLLAMA_MODEL", "llama3"),
        patch("src.main.httpx.post", side_effect=error),
    ):
        response = client.get("/api/v1/ollama/test")
    assert response.status_code == 503
    assert response.json()["detail"]["ollama_status"] == 404


def test_ollama_test_http_error():
    with (
        patch("src.main.OLLAMA_MODEL", "llama3"),
        patch("src.main.httpx.post", side_effect=httpx.ConnectError("offline")),
    ):
        response = client.get("/api/v1/ollama/test")
    assert response.status_code == 503
