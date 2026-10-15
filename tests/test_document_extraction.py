"""Service checks against PostgreSQL and temporary local document storage."""

import hashlib
import uuid

import pytest
from sqlalchemy import func, select
from tests.sample_data import make_pdf

from src.document_extraction import (
    DocumentNotFoundError,
    UnsupportedDocumentTypeError,
    extract_document,
)
from src.models import Client, ExtractedText, SourceDocument


@pytest.mark.parametrize(
    ("filename", "data", "expected"),
    [
        ("transcript.TXT", b"Alice: Hello.  \r\n", "Alice: Hello."),
        (
            "transcript.md",
            b"# Meeting\n\n**Alice:** Hello.",
            "Meeting\n\nAlice: Hello.",
        ),
        ("transcript.markdown", b"**Alice:** Hello.", "Alice: Hello."),
        (
            "transcript.pdf",
            make_pdf(["Alice: Hello.", "Bob: Hi."]),
            "Alice: Hello.\n\nBob: Hi.",
        ),
    ],
)
def test_extracts_and_persists_supported_files(
    db_session, storage, demo_client, stored_document, filename, data, expected
):
    document = stored_document(data, filename)
    document_id = document.id
    key = document.storage_key

    result = extract_document(demo_client.id, document_id, db_session, storage)
    assert result.document_id == document_id
    assert result.extracted_at.tzinfo is not None
    db_session.expunge_all()

    assert db_session.get(ExtractedText, document_id).text == expected
    original = db_session.get(SourceDocument, document_id)
    assert original.sha256 == hashlib.sha256(data).hexdigest()
    assert original.size_bytes == len(data)
    assert original.original_filename == filename
    assert storage.read(key) == data


@pytest.mark.parametrize(
    ("content_type", "data", "expected"),
    [
        ("TEXT/PLAIN; charset=utf-8", b"Alice: Hello.", "Alice: Hello."),
        ("text/markdown", b"**Alice:** Hello.", "Alice: Hello."),
        ("text/x-markdown", b"**Alice:** Hello.", "Alice: Hello."),
        ("application/pdf", make_pdf(["Alice: Hello."]), "Alice: Hello."),
    ],
)
def test_uses_mime_type_for_extensionless_files(
    db_session, storage, demo_client, stored_document, content_type, data, expected
):
    document = stored_document(data, "transcript", content_type)

    result = extract_document(demo_client.id, document.id, db_session, storage)

    assert result.text == expected


def test_reuses_saved_result_without_reading_file_again(
    db_session, storage, demo_client, stored_document, monkeypatch
):
    document = stored_document()
    first = extract_document(demo_client.id, document.id, db_session, storage)
    timestamp = first.extracted_at

    def unexpected_read(key):
        pytest.fail("A saved extraction should not read the original again")

    monkeypatch.setattr(storage, "read", unexpected_read)
    second = extract_document(demo_client.id, document.id, db_session, storage)

    assert second.text == first.text
    assert second.extracted_at == timestamp
    assert db_session.scalar(select(func.count()).select_from(ExtractedText)) == 1


@pytest.mark.parametrize("other_client", [False, True])
def test_unknown_or_other_clients_document_is_not_found(
    db_session, storage, demo_client, stored_document, monkeypatch, other_client
):
    client_id = demo_client.id
    document_id = uuid.uuid4()
    if other_client:
        document_id = stored_document().id
        other = Client(name="Other client")
        db_session.add(other)
        db_session.commit()
        client_id = other.id

    def unexpected_read(key):
        pytest.fail("Missing or unauthorized documents must not read storage")

    monkeypatch.setattr(storage, "read", unexpected_read)
    with pytest.raises(DocumentNotFoundError, match="Document not found"):
        extract_document(client_id, document_id, db_session, storage)

    assert db_session.scalar(select(func.count()).select_from(ExtractedText)) == 0


def test_other_client_cannot_access_saved_result(
    db_session, storage, demo_client, stored_document, client_factory
):
    owner = client_factory("Other client")
    document = stored_document(owner=owner)
    document_id = document.id
    assert document.client_id == owner.id
    assert document.storage_key == f"{owner.id}/{document_id}"
    assert storage.read(document.storage_key) == b"Alice: Hello.  \r\n"
    saved = extract_document(owner.id, document_id, db_session, storage)
    saved_text = saved.text

    with pytest.raises(DocumentNotFoundError, match="Document not found"):
        extract_document(demo_client.id, document_id, db_session, storage)

    assert db_session.get(ExtractedText, document_id).text == saved_text


@pytest.mark.parametrize("filename", ["transcript.docx", "transcript"])
def test_rejects_unsupported_types(
    db_session, storage, demo_client, stored_document, monkeypatch, filename
):
    # A known MIME type must not override an explicitly unsupported extension.
    content_type = (
        "text/plain" if filename.endswith(".docx") else "application/octet-stream"
    )
    document = stored_document(filename=filename, content_type=content_type)

    def unexpected_read(key):
        pytest.fail("Unsupported formats must be rejected before reading storage")

    monkeypatch.setattr(storage, "read", unexpected_read)
    with pytest.raises(UnsupportedDocumentTypeError):
        extract_document(demo_client.id, document.id, db_session, storage)

    assert db_session.get(ExtractedText, document.id) is None


def test_missing_stored_file_leaves_document_unchanged(
    db_session, storage, demo_client, stored_document
):
    document = stored_document()
    document_id = document.id
    storage.delete(document.storage_key)

    with pytest.raises(FileNotFoundError):
        extract_document(demo_client.id, document_id, db_session, storage)

    assert db_session.get(ExtractedText, document_id) is None
    assert db_session.get(SourceDocument, document_id) is not None


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("transcript.txt", b"\xff"),
        ("transcript.md", b"---"),
        ("transcript.pdf", b"not a PDF"),
    ],
)
def test_extraction_failure_leaves_no_result_and_preserves_original(
    db_session, storage, demo_client, stored_document, filename, data
):
    document = stored_document(data, filename)
    document_id = document.id
    key = document.storage_key

    with pytest.raises(ValueError):
        extract_document(demo_client.id, document_id, db_session, storage)

    assert db_session.get(ExtractedText, document_id) is None
    assert db_session.get(SourceDocument, document_id) is not None
    assert storage.read(key) == data


def test_commit_failure_rolls_back_result_and_preserves_upload(
    db_session, storage, demo_client, stored_document, monkeypatch
):
    document = stored_document()
    document_id = document.id
    key = document.storage_key

    def failing_commit():
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        extract_document(demo_client.id, document_id, db_session, storage)

    assert db_session.get(ExtractedText, document_id) is None
    assert db_session.get(SourceDocument, document_id) is not None
    assert storage.read(key) == b"Alice: Hello.  \r\n"
