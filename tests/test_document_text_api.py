"""HTTP checks for upload, extraction, persisted text, and client scoping."""

import hashlib
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.sample_data import make_pdf

from src.main import app
from src.models import Client, ExtractedText, SourceDocument


def document_url(client_id, document_id) -> str:
    return f"/clients/{client_id}/documents/{document_id}"


def upload_document(
    client,
    client_id,
    data=b"Alice: Hello.  \r\n",
    filename="transcript.txt",
    content_type="application/octet-stream",
) -> dict:
    response = client.post(
        f"/clients/{client_id}/documents",
        files={"file": (filename, data, content_type)},
    )
    assert response.status_code == 201
    return response.json()


def store_legacy_document(db, storage, client_id, data, filename):
    """Represent files saved before upload validation was introduced."""
    document_id = uuid.uuid4()
    document = SourceDocument(
        id=document_id,
        client_id=client_id,
        original_filename=filename,
        content_type="application/octet-stream",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=f"{client_id}/{document_id}",
    )
    storage.save(document.storage_key, data)
    db.add(document)
    db.commit()
    return document_id


@pytest.mark.parametrize(
    ("filename", "data", "content_type", "expected"),
    [
        ("transcript.txt", b"Alice: Hello.  \r\n", "text/plain", "Alice: Hello."),
        (
            "transcript.md",
            b"# Meeting\n\n**Alice:** Hello.",
            "text/markdown",
            "Meeting\n\nAlice: Hello.",
        ),
        (
            "transcript.pdf",
            make_pdf(["Alice: Hello.", "Bob: Hi."]),
            "application/pdf",
            "Alice: Hello.\n\nBob: Hi.",
        ),
        (
            "transcript",
            "Alice: Café 你好 👋".encode("utf-16"),
            "text/plain",
            "Alice: Café 你好 👋",
        ),
    ],
)
def test_upload_extract_and_retrieve_text(
    client, db_session, storage, demo_client, filename, data, content_type, expected
):
    uploaded = upload_document(client, demo_client.id, data, filename, content_type)
    url = document_url(demo_client.id, uploaded["id"])

    response = client.post(f"{url}/extract")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"document_id", "text", "extracted_at"}
    assert body["document_id"] == uploaded["id"]
    assert body["text"] == expected
    assert datetime.fromisoformat(body["extracted_at"]).tzinfo is not None
    db_session.expunge_all()

    retrieved = client.get(f"{url}/text")
    assert retrieved.status_code == 200
    assert retrieved.json() == body
    assert client.get(url).json() == uploaded
    document = db_session.get(SourceDocument, uuid.UUID(uploaded["id"]))
    assert storage.read(document.storage_key) == data


def test_repeated_extraction_returns_same_result(client, db_session, demo_client):
    uploaded = upload_document(client, demo_client.id)
    url = document_url(demo_client.id, uploaded["id"])

    first = client.post(f"{url}/extract")
    second = client.post(f"{url}/extract")

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert db_session.scalar(select(func.count()).select_from(ExtractedText)) == 1


def test_get_before_extraction_returns_404(client, db_session, demo_client):
    uploaded = upload_document(client, demo_client.id)
    url = document_url(demo_client.id, uploaded["id"])

    response = client.get(f"{url}/text")

    assert response.status_code == 404
    assert response.json() == {"detail": "Extracted text not found"}
    assert db_session.get(ExtractedText, uuid.UUID(uploaded["id"])) is None


@pytest.mark.parametrize(("method", "suffix"), [("POST", "extract"), ("GET", "text")])
def test_unknown_document_returns_404(client, demo_client, method, suffix):
    url = document_url(demo_client.id, uuid.uuid4())

    response = client.request(method, f"{url}/{suffix}")

    assert response.status_code == 404


@pytest.mark.parametrize(("method", "suffix"), [("POST", "extract"), ("GET", "text")])
@pytest.mark.parametrize("already_extracted", [False, True])
def test_another_clients_document_matches_unknown_document(
    client, db_session, demo_client, method, suffix, already_extracted
):
    uploaded = upload_document(client, demo_client.id)
    original_url = document_url(demo_client.id, uploaded["id"])
    if already_extracted:
        assert client.post(f"{original_url}/extract").status_code == 200
    other = Client(name="Other client")
    db_session.add(other)
    db_session.commit()
    other_url = document_url(other.id, uploaded["id"])
    unknown_url = document_url(other.id, uuid.uuid4())

    response = client.request(method, f"{other_url}/{suffix}")
    unknown = client.request(method, f"{unknown_url}/{suffix}")

    assert response.status_code == unknown.status_code == 404
    assert response.json() == unknown.json()
    expected_count = 1 if already_extracted else 0
    assert (
        db_session.scalar(select(func.count()).select_from(ExtractedText))
        == expected_count
    )


@pytest.mark.parametrize(("method", "suffix"), [("POST", "extract"), ("GET", "text")])
def test_invalid_document_id_returns_422(client, demo_client, method, suffix):
    url = document_url(demo_client.id, "not-a-uuid")

    assert client.request(method, f"{url}/{suffix}").status_code == 422


def test_unsupported_format_returns_415(client, db_session, storage, demo_client):
    document_id = store_legacy_document(
        db_session, storage, demo_client.id, b"hello", "transcript.docx"
    )
    url = document_url(demo_client.id, document_id)

    response = client.post(f"{url}/extract")

    assert response.status_code == 415
    assert response.json() == {
        "detail": "Supported document formats are TXT, Markdown, and PDF"
    }
    assert db_session.get(ExtractedText, document_id) is None


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("transcript.txt", b"\xff"),
        ("transcript.txt", b" \t\r\n"),
        ("transcript.md", b"---"),
        ("transcript.pdf", b"not a PDF"),
        ("transcript.pdf", make_pdf(["Alice: Hello."], password="secret")),
        ("transcript.pdf", make_pdf([None])),
    ],
)
def test_invalid_content_returns_422_and_preserves_upload(
    client, db_session, storage, demo_client, filename, data
):
    document_id = store_legacy_document(
        db_session, storage, demo_client.id, data, filename
    )
    url = document_url(demo_client.id, document_id)
    uploaded = client.get(url).json()

    response = client.post(f"{url}/extract")

    assert response.status_code == 422
    assert response.json()["detail"]
    assert client.get(f"{url}/text").status_code == 404
    assert client.get(url).json() == uploaded
    document = db_session.get(SourceDocument, document_id)
    assert storage.read(document.storage_key) == data


def test_missing_stored_file_returns_409(client, db_session, storage, demo_client):
    uploaded = upload_document(client, demo_client.id)
    document_id = uuid.UUID(uploaded["id"])
    document = db_session.get(SourceDocument, document_id)
    storage.delete(document.storage_key)
    url = document_url(demo_client.id, document_id)

    response = client.post(f"{url}/extract")

    assert response.status_code == 409
    assert response.json() == {"detail": "Stored document file is unavailable"}
    assert db_session.get(ExtractedText, document_id) is None
    assert client.get(url).json() == uploaded


def test_storage_failure_returns_503_without_internal_details(
    client, db_session, storage, demo_client, monkeypatch
):
    uploaded = upload_document(client, demo_client.id)
    document_id = uuid.UUID(uploaded["id"])
    url = document_url(demo_client.id, document_id)

    def failing_read(key):
        raise PermissionError("internal storage path and permission details")

    monkeypatch.setattr(storage, "read", failing_read)
    response = client.post(f"{url}/extract")

    assert response.status_code == 503
    assert response.json() == {"detail": "Document storage is unavailable"}
    assert db_session.get(ExtractedText, document_id) is None


def test_database_failure_returns_500_without_saving_partial_result(
    client, db_session, storage, demo_client, monkeypatch
):
    uploaded = upload_document(client, demo_client.id)
    document_id = uuid.UUID(uploaded["id"])
    url = document_url(demo_client.id, document_id)

    def failing_commit():
        raise RuntimeError("internal database failure")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    # Use the fixture's dependency overrides, but observe the HTTP 500 instead
    # of TestClient re-raising the unhandled application exception.
    response = TestClient(app, raise_server_exceptions=False).post(f"{url}/extract")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert db_session.get(ExtractedText, document_id) is None
    original = db_session.get(SourceDocument, document_id)
    assert original is not None
    assert storage.read(original.storage_key) == b"Alice: Hello.  \r\n"
