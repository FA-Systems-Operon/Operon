"""Endpoints for client documents, metadata, and extracted plain text."""

import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import settings
from src.db import get_db
from src.document_extraction import (
    DocumentNotFoundError,
    UnsupportedDocumentTypeError,
    extract_document,
    validate_document,
)
from src.models import Client, ExtractedText, SourceDocument
from src.schemas import ExtractedTextOut, SourceDocumentOut
from src.storage import DocumentStorage, get_storage

router = APIRouter(prefix="/api/v1/clients/{client_id}/documents", tags=["documents"])

# Shorthands so each endpoint can just say "db: DbSession" and "storage: Storage".
DbSession = Annotated[Session, Depends(get_db)]
Storage = Annotated[DocumentStorage, Depends(get_storage)]


@router.get("", response_model=list[SourceDocumentOut])
def list_documents(client_id: uuid.UUID, db: DbSession) -> list[SourceDocument]:
    """Return all documents belonging to a client."""
    if db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return list(
        # method used to execute a query and return a specialized iterator that yields database ORM objects or single values directly instead of needing to manually extract them
        db.scalars(
            select(SourceDocument)
            .where(SourceDocument.client_id == client_id)
            .order_by(SourceDocument.uploaded_at)
        )
    )


@router.post("", response_model=SourceDocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    client_id: uuid.UUID, file: UploadFile, db: DbSession, storage: Storage
) -> SourceDocument:
    """Store an uploaded file against a client and record its metadata."""
    if db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")

    # Read one byte past the limit: if we get it, the file is too big.
    data = file.file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File is larger than {settings.MAX_UPLOAD_BYTES} bytes",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty")

    # The storage key is built only from IDs we generate. The user's filename is
    # stored as metadata and never used as a path.
    document_id = uuid.uuid4()
    storage_key = f"{client_id}/{document_id}"

    document = SourceDocument(
        id=document_id,
        client_id=client_id,
        original_filename=(file.filename or "unnamed")[:255],
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=storage_key,
    )
    try:
        validate_document(document, data)
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    storage.save(storage_key, data)
    db.add(document)
    try:
        db.commit()
    except Exception:
        # Don't leave a file in storage that no database row points to.
        storage.delete(storage_key)
        raise
    db.refresh(document)  # loads uploaded_at, which Postgres fills in
    return document


@router.post("/{document_id}/extract", response_model=ExtractedTextOut)
def extract_document_text(
    client_id: uuid.UUID,
    document_id: uuid.UUID,
    db: DbSession,
    storage: Storage,
    force: Annotated[
        bool,
        Query(
            description="Re-extract with the current extractor, replacing saved text"
        ),
    ] = False,
) -> ExtractedText:
    """Extract and save a client's document text, or return its saved result."""
    try:
        return extract_document(client_id, document_id, db, storage, force=force)
    except DocumentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found") from exc
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Stored document file is unavailable"
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Document storage is unavailable"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/{document_id}/text", response_model=ExtractedTextOut)
def get_document_text(
    client_id: uuid.UUID, document_id: uuid.UUID, db: DbSession
) -> ExtractedText:
    """Read saved text without performing extraction; scope lookup to the client."""
    result = db.scalar(
        select(ExtractedText)
        .join(ExtractedText.document)
        .where(
            ExtractedText.document_id == document_id,
            SourceDocument.client_id == client_id,
        )
    )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extracted text not found")
    return result


@router.get("/{document_id}", response_model=SourceDocumentOut)
def get_document(
    client_id: uuid.UUID, document_id: uuid.UUID, db: DbSession
) -> SourceDocument:
    """Return a document's metadata, only if it belongs to this client."""
    # Filtering on client_id as well as id keeps clients isolated: another
    # client's document ID gets the same 404 as an ID that doesn't exist.
    document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.id == document_id, SourceDocument.client_id == client_id
        )
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document
