"""PostgreSQL checks for extracted-text persistence and document constraints."""

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, insert
from sqlalchemy.exc import IntegrityError

from src.models import ExtractedText, SourceDocument


@pytest.fixture
def source_document(db_session, demo_client):
    document_id = uuid.uuid4()
    data = b"Alice: Hello."
    document = SourceDocument(
        id=document_id,
        client_id=demo_client.id,
        original_filename="transcript.txt",
        content_type="text/plain",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=f"{demo_client.id}/{document_id}",
    )
    db_session.add(document)
    db_session.commit()
    return document


def test_stores_unicode_text_and_extraction_timestamp(db_session, source_document):
    document_id = source_document.id
    content = "[00:01] Alice: Café 你好 👋\n\n[00:02] Bob: Keep  two spaces.\n" * 40
    db_session.add(ExtractedText(document=source_document, text=content))
    db_session.commit()
    db_session.expunge_all()

    stored = db_session.get(ExtractedText, document_id)
    assert stored is not None
    assert stored.text == content
    assert stored.extracted_at.tzinfo is not None
    assert stored.document.original_filename == "transcript.txt"
    assert stored.document.sha256 == hashlib.sha256(b"Alice: Hello.").hexdigest()
    assert stored.document.extracted_text is stored


def test_updating_text_refreshes_extraction_timestamp(db_session, source_document):
    original_timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc)
    result = ExtractedText(
        document=source_document,
        text="First result",
        extracted_at=original_timestamp,
    )
    db_session.add(result)
    db_session.commit()

    result.text = "Updated result"
    db_session.commit()
    db_session.refresh(result)

    assert result.text == "Updated result"
    assert result.extracted_at > original_timestamp
    assert result.extracted_at.tzinfo is not None


def test_document_can_exist_without_extracted_text(db_session, source_document):
    assert source_document.extracted_text is None
    assert db_session.get(ExtractedText, source_document.id) is None


def test_rejects_second_text_record_for_same_document(db_session, source_document):
    document_id = source_document.id
    db_session.add(ExtractedText(document_id=document_id, text="First result"))
    db_session.commit()

    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(ExtractedText).values(document_id=document_id, text="Second result")
        )
    db_session.rollback()

    assert db_session.get(ExtractedText, document_id).text == "First result"


def test_rejects_text_for_missing_document(db_session):
    with pytest.raises(IntegrityError):
        db_session.execute(
            insert(ExtractedText).values(document_id=uuid.uuid4(), text="Orphan result")
        )
    db_session.rollback()


def test_database_deletion_removes_derived_text(db_session, source_document):
    document_id = source_document.id
    db_session.add(ExtractedText(document_id=document_id, text="Derived text"))
    db_session.commit()

    db_session.execute(delete(SourceDocument).where(SourceDocument.id == document_id))
    db_session.commit()

    assert db_session.get(ExtractedText, document_id) is None


@pytest.mark.parametrize("load_text", [False, True])
def test_orm_deletion_removes_derived_text(db_session, source_document, load_text):
    document_id = source_document.id
    db_session.add(ExtractedText(document_id=document_id, text="Derived text"))
    db_session.commit()
    if load_text:
        assert source_document.extracted_text is not None

    db_session.delete(source_document)
    db_session.commit()

    assert db_session.get(ExtractedText, document_id) is None


def test_removing_extraction_preserves_source_document(db_session, source_document):
    document_id = source_document.id
    source_document.extracted_text = ExtractedText(text="Derived text")
    db_session.commit()

    source_document.extracted_text = None
    db_session.commit()

    assert db_session.get(ExtractedText, document_id) is None
    assert db_session.get(SourceDocument, document_id) is not None
