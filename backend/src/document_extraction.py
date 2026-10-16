"""Connect stored uploads, format-specific extractors, and text persistence."""

import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.markdown_extraction import extract_markdown
from src.models import ExtractedText, SourceDocument
from src.pdf_extraction import extract_pdf
from src.storage import DocumentStorage
from src.txt_extraction import extract_txt


class DocumentNotFoundError(LookupError):
    """The document does not exist or belongs to another client."""


class UnsupportedDocumentTypeError(ValueError):
    """The upload is outside the supported TXT, Markdown, and PDF formats."""


def _extractor_for(document: SourceDocument) -> Callable[[bytes], str]:
    extension = Path(document.original_filename).suffix.lower()
    if extension:
        extractor = {
            ".txt": extract_txt,
            ".md": extract_markdown,
            ".markdown": extract_markdown,
            ".pdf": extract_pdf,
        }.get(extension)
    else:
        content_type = document.content_type.split(";", 1)[0].strip().lower()
        extractor = {
            "text/plain": extract_txt,
            "text/markdown": extract_markdown,
            "text/x-markdown": extract_markdown,
            "application/pdf": extract_pdf,
        }.get(content_type)
    if extractor is None:
        raise UnsupportedDocumentTypeError(
            "Supported document formats are TXT, Markdown, and PDF"
        )
    return extractor


def validate_document(document: SourceDocument, data: bytes) -> None:
    """Check supported format and readable content without saving extracted text."""
    _extractor_for(document)(data)


def extract_document(
    client_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session,
    storage: DocumentStorage,
    *,
    force: bool = False,
) -> ExtractedText:
    """Extract and commit text for a client's document, or reuse its saved result.

    Lock the source row until the transaction ends so repeated requests cannot
    create competing results. With force=True, replace saved text using the
    current extractor and refresh its timestamp, even if the text is unchanged.
    Extraction failures preserve both the upload and any previously saved text.
    Commit on success and roll back the session on any failure. Missing files
    and extractor errors propagate for the API layer to handle later.
    """
    try:
        document = db.scalar(
            select(SourceDocument)
            .where(
                SourceDocument.id == document_id, SourceDocument.client_id == client_id
            )
            .with_for_update()
        )
        if document is None:
            raise DocumentNotFoundError("Document not found")

        result = db.get(ExtractedText, document_id)
        if result is None or force:
            extractor = _extractor_for(document)
            data = storage.read(document.storage_key)
            text = extractor(data)
            if result is None:
                result = ExtractedText(document_id=document_id, text=text)
                db.add(result)
            else:
                result.text = text
                result.extracted_at = func.now()
            db.flush()
            db.refresh(result)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
