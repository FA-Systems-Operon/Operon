"""Database tables for clients and the source documents uploaded for them."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class Client(Base):
    """A business client. Every source document belongs to exactly one client."""

    __tablename__ = "clients"

    # uuid.UUID maps to Postgres's native UUID type.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    documents: Mapped[list["SourceDocument"]] = relationship(back_populates="client")


class SourceDocument(Base):
    """Metadata for an uploaded file. The file itself lives in storage, not the DB."""

    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # No ON DELETE CASCADE: a client with documents can't be deleted by accident,
    # which would leave their files orphaned in storage.
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Hex SHA-256 of the file contents, for integrity checks and spotting duplicates.
    sha256: Mapped[str] = mapped_column(String(64))
    # Where the storage backend keeps the file (e.g. "<client_id>/<document_id>").
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    client: Mapped[Client] = relationship(back_populates="documents")
    extracted_text: Mapped["ExtractedText | None"] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class ExtractedText(Base):
    """Derived plain text for a source document, stored separately from its file."""

    __tablename__ = "extracted_texts"

    # Using the document ID as the primary key enforces one result per document.
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), primary_key=True
    )
    text: Mapped[str] = mapped_column(Text)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped[SourceDocument] = relationship(back_populates="extracted_text")
