"""Database tables for clients and the source documents uploaded for them."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
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


class ClientProfile(Base):
    """A profile associated with a client. Versioned — never mutate, always append."""

    __tablename__ = "client_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    versions: Mapped[list["ClientProfileVersion"]] = relationship(
        back_populates="profile"
    )


class ClientProfileVersion(Base):
    """An immutable snapshot of a ClientProfile at a point in time.

    Never update an existing row — insert a new one with an incremented version_number.
    The data column is a placeholder until the profile schema is defined.
    """

    __tablename__ = "client_profile_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_profiles.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Placeholder: replace with typed columns once the profile schema is agreed on.
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profile: Mapped[ClientProfile] = relationship(back_populates="versions")


class Playbook(Base):
    """A shared context/knowledge store. Versioned — never mutate, always append."""

    __tablename__ = "playbooks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    versions: Mapped[list["PlaybookVersion"]] = relationship(back_populates="playbook")


class PlaybookVersion(Base):
    """An immutable snapshot of a Playbook at a point in time.

    Never update an existing row — insert a new one with an incremented version_number.
    The data column is a placeholder until the playbook schema is defined.
    """

    __tablename__ = "playbook_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    playbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playbooks.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Placeholder: replace with typed columns once the playbook schema is agreed on.
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    playbook: Mapped[Playbook] = relationship(back_populates="versions")
