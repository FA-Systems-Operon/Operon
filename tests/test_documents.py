"""Tests for the document endpoints: upload and metadata lookup."""

import hashlib
import uuid

import pytest
from sqlalchemy import func, select
from tests.test_pdf_extraction import make_pdf

from src.config import settings
from src.models import Client, SourceDocument


def documents_url(client_id) -> str:
    return f"/clients/{client_id}/documents"


def stored_files(tmp_path) -> list:
    """All files in the test storage folder (empty folders don't count)."""
    return [path for path in tmp_path.rglob("*") if path.is_file()]


# --- POST /clients/{client_id}/documents ---


def test_upload_succeeds(client, db_session, storage, demo_client):
    content = make_pdf(["Demo onboarding brief"])
    response = client.post(
        documents_url(demo_client.id),
        files={"file": ("brief.pdf", content, "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["client_id"] == str(demo_client.id)
    assert body["original_filename"] == "brief.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()

    # The metadata row was saved against the right client...
    document = db_session.get(SourceDocument, uuid.UUID(body["id"]))
    assert document is not None
    assert document.client_id == demo_client.id
    # ...and the file is on disk (in tmp_path) with the same contents.
    assert storage.read(document.storage_key) == content


def test_upload_unknown_client_returns_404(client, tmp_path):
    response = client.post(
        documents_url(uuid.uuid4()), files={"file": ("a.txt", b"hi")}
    )

    assert response.status_code == 404
    assert stored_files(tmp_path) == []


def test_upload_without_file_returns_422(client, demo_client):
    response = client.post(documents_url(demo_client.id))

    assert response.status_code == 422


def test_upload_empty_file_returns_400(client, demo_client, tmp_path):
    response = client.post(
        documents_url(demo_client.id), files={"file": ("a.txt", b"")}
    )

    assert response.status_code == 400
    assert stored_files(tmp_path) == []


def test_upload_too_large_returns_413(client, demo_client, tmp_path, monkeypatch):
    # Lower the limit for this test only, instead of uploading 20 MB.
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)

    response = client.post(
        documents_url(demo_client.id), files={"file": ("a.txt", b"x" * 11)}
    )

    assert response.status_code == 413
    assert stored_files(tmp_path) == []


def test_upload_deletes_file_if_db_commit_fails(
    client, db_session, demo_client, tmp_path, monkeypatch
):
    def failing_commit():
        raise RuntimeError("simulated database failure")

    # The app uses this same session (see conftest), so its commit() will fail.
    monkeypatch.setattr(db_session, "commit", failing_commit)
    url = documents_url(demo_client.id)
    files = {"file": ("a.txt", b"hi")}

    # TestClient re-raises errors from the app instead of returning a 500.
    # Only the request is inside the block, so we know it's what raised.
    with pytest.raises(RuntimeError, match="simulated database failure"):
        client.post(url, files=files)

    # The file was saved before the commit, then cleaned up: no orphans.
    assert stored_files(tmp_path) == []


# --- GET /clients/{client_id}/documents/{document_id} ---


def upload(client, client_id) -> dict:
    """Upload a small file through the API and return the response JSON."""
    response = client.post(documents_url(client_id), files={"file": ("a.txt", b"hi")})
    assert response.status_code == 201
    return response.json()


def test_get_document_returns_metadata(client, demo_client):
    uploaded = upload(client, demo_client.id)

    response = client.get(f"{documents_url(demo_client.id)}/{uploaded['id']}")

    assert response.status_code == 200
    assert response.json() == uploaded


def test_get_document_of_another_client_returns_404(client, db_session, demo_client):
    uploaded = upload(client, demo_client.id)
    other_client = Client(name="Other Client")
    db_session.add(other_client)
    db_session.commit()

    # Client isolation: asking for demo_client's document under another client's
    # URL must look exactly like the document doesn't exist.
    response = client.get(f"{documents_url(other_client.id)}/{uploaded['id']}")

    assert response.status_code == 404


def test_get_unknown_document_returns_404(client, demo_client):
    response = client.get(f"{documents_url(demo_client.id)}/{uuid.uuid4()}")

    assert response.status_code == 404


# --- GET /clients/{client_id}/documents ---


def test_list_dofor_client(client, db_session, demo_client):
    upload(client, demo_client.id)
    upload(client, demo_client.id)

    response = client.get(documents_url(demo_client.id))

    assert response.status_code == 200
    assert len(response.json()) == 2


# no docs yet
def test_list_documents_empty_for_new_client(client, demo_client):
    response = client.get(documents_url(demo_client.id))

    assert response.status_code == 200
    assert response.json() == []


def test_list_documents_unknown_client(client):
    response = client.get(documents_url(uuid.uuid4()))

    assert response.status_code == 404


# docs from other clients are not returned
def test_list_documents_excludes_other_clients(client, db_session, demo_client):
    upload(client, demo_client.id)
    other_client = Client(name="Other Client")
    db_session.add(other_client)
    db_session.commit()
    upload(client, other_client.id)

    response = client.get(documents_url(demo_client.id))

    assert len(response.json()) == 1
    assert response.json()[0]["client_id"] == str(demo_client.id)


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected_status"),
    [
        ("brief.docx", b"hello", "text/plain", 415),
        ("brief", b"hello", "application/octet-stream", 415),
        ("brief.txt", b"\xff", "text/plain", 422),
        ("brief.txt", b" \t\n", "text/plain", 422),
        ("brief.md", b"---", "text/markdown", 422),
        ("brief.pdf", b"not a PDF", "application/pdf", 422),
        ("brief.pdf", make_pdf([None]), "application/pdf", 422),
        ("brief.pdf", make_pdf(["hello"], password="secret"), "application/pdf", 422),
    ],
)
def test_invalid_upload_leaves_no_document_or_file(
    client,
    db_session,
    demo_client,
    tmp_path,
    filename,
    content,
    content_type,
    expected_status,
):
    response = client.post(
        documents_url(demo_client.id),
        files={"file": (filename, content, content_type)},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]
    assert db_session.scalar(select(func.count()).select_from(SourceDocument)) == 0
    assert stored_files(tmp_path) == []
