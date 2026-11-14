"""Database tables for clients and the source documents uploaded for them."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, MappedColumn, mapped_column, relationship

from src.db import Base


class ReviewStatus(str, enum.Enum):
    """Where a profile, playbook or artifact version is in the review process."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"


def _status_column() -> MappedColumn[ReviewStatus]:
    """Same status column for every kind of version (stored as text, not a Postgres enum)."""
    return mapped_column(
        Enum(
            ReviewStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [member.value for member in e],
        ),
        default=ReviewStatus.DRAFT,
        nullable=False,
        index=True,
    )


class DocumentKind(str, enum.Enum):
    """What a source document is, so agents and reviewers can tell sources apart."""

    TRANSCRIPT = "transcript"
    INTAKE = "intake"


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
    # NULL for documents uploaded before kinds existed, or without one.
    kind: Mapped[DocumentKind | None] = mapped_column(
        Enum(
            DocumentKind,
            native_enum=False,
            length=20,
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=True,
    )
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
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[SourceDocument] = relationship(back_populates="extracted_text")


class JobStatus(str, enum.Enum):
    """Where an onboarding-agent run is. #37 adds recovery and retries on top."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OnboardingJob(Base):
    """One onboarding-agent run on a client's transcript and intake answers (#36).

    A job is started once both files are uploaded, never on a single upload, so
    the agent always drafts from a complete set. The two documents are pinned
    on the job: the agent reads exactly these, not whatever else the client has.
    One job per transcript/intake pair, so asking again returns the same job.

    The row is committed as pending before anything runs, so a crash can't lose
    it (#37). A runner claims it with a lease; if the lease runs out before the
    job finishes, the worker treats it as abandoned and retries it.
    """

    __tablename__ = "onboarding_jobs"
    __table_args__ = (UniqueConstraint("transcript_document_id", "intake_document_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    transcript_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id"), index=True
    )
    intake_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id"), index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            native_enum=False,
            length=20,
            values_callable=lambda e: [member.value for member in e],
        ),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    # Short, user-safe reason when status is failed; details go to the server log.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The draft profile version this run produced, when it succeeded.
    result_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client_profile_versions.id"), nullable=True
    )
    # How many times a runner has claimed this job, including the current run.
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # While running: when the claim expires and the job counts as abandoned.
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # While pending after a failed attempt: don't retry before this time.
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    result_version: Mapped["ClientProfileVersion | None"] = relationship()

    @property
    def result_profile_id(self) -> uuid.UUID | None:
        """The profile the draft belongs to; a link to the draft needs both IDs."""
        version = self.result_version
        return version.client_profile_id if version else None


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

    Never overwrite snapshot data — insert a new row with an incremented version_number.
    Approval metadata may be set separately by the approval workflow.
    The data column is a placeholder until the profile schema is defined.
    """

    __tablename__ = "client_profile_versions"
    __table_args__ = (UniqueConstraint("client_profile_id", "version_number"),)
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
    status: Mapped[ReviewStatus] = _status_column()
    # TODO: make approved_by a foreign key to users once authentication exists.
    approved_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    """An immutable snapshot of a Playbook samething as clientprofileversion"""

    __tablename__ = "playbook_versions"
    __table_args__ = (UniqueConstraint("playbook_id", "version_number"),)

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
    status: Mapped[ReviewStatus] = _status_column()
    approved_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    playbook: Mapped[Playbook] = relationship(back_populates="versions")


class Artifact(Base):
    """A logical deliverable for a client"""

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    versions: Mapped[list["ArtifactVersion"]] = relationship(back_populates="artifact")


class ArtifactVersion(Base):
    """
    Output based on the current latest version inputs.
    The two input foreign keys are what make staleness detectable.
    Becomes stale once either or both inputs are stale.
    """

    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    client_profile_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_profile_versions.id"), index=True
    )
    playbook_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("playbook_versions.id"), index=True, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[ReviewStatus] = _status_column()
    approved_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Why/when it went stale. approved_at is kept so history shows it WAS approved.
    stale_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    artifact: Mapped[Artifact] = relationship(back_populates="versions")


# --- Immutability guard START -----------------
_IMMUTABLE = {
    ClientProfileVersion: ("data", "version_number", "client_profile_id"),
    PlaybookVersion: ("data", "version_number", "playbook_id"),
    ArtifactVersion: (
        "data",
        "version_number",
        "artifact_id",
        "client_profile_version_id",
        "playbook_version_id",
    ),
}


def _make_guard(fields: tuple[str, ...]):
    def guard(mapper, connection, target):
        state = inspect(target)
        for name in fields:
            if state.attrs[name].history.has_changes():
                raise ValueError(
                    f"{type(target).__name__}.{name} is immutable; create a new version"
                )
        approved = state.attrs.approved_at.history
        if (
            approved.has_changes()
            and approved.deleted
            and approved.deleted[0] is not None
        ):
            raise ValueError("approved_at is already set and cannot be changed")

    return guard


for _model, _fields in _IMMUTABLE.items():
    event.listen(_model, "before_update", _make_guard(_fields))
# ------Immutability guard  END----------------
