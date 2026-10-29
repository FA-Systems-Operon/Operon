"""Pydantic models that define the JSON shape of API requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models import DocumentKind, ReviewStatus

# What the API user sends


class ClientIn(BaseModel):
    """Request body for creating a client."""

    name: str = Field(min_length=1, max_length=255)


# Returned — includes the server-generated id and timestamp


class ClientOut(BaseModel):
    """A client record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class SourceDocumentOut(BaseModel):
    """Metadata returned for an uploaded document.

    storage_key is left out on purpose: where the file lives is an internal detail.
    """

    # Lets FastAPI build this directly from a SourceDocument database object.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    kind: DocumentKind | None
    uploaded_at: datetime


class ExtractedTextOut(BaseModel):
    """Saved plain text returned after extraction or a text lookup."""

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    text: str
    extracted_at: datetime


class ClientProfileOut(BaseModel):
    """A client profile record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    created_at: datetime


class ClientProfileVersionOut(BaseModel):
    """A single immutable version of a client profile."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_profile_id: uuid.UUID
    version_number: int
    status: ReviewStatus
    data: dict
    created_at: datetime
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None


class PlaybookOut(BaseModel):
    """A playbook record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class PlaybookVersionOut(BaseModel):
    """A single immutable version of a playbook."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    playbook_id: uuid.UUID
    version_number: int
    status: ReviewStatus
    data: dict
    created_at: datetime
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None


class ApproveIn(BaseModel):
    """Who is approving. TODO: derive from the authenticated user once auth exists."""

    approved_by: uuid.UUID


class ProfileApprovalOut(BaseModel):
    """Result of approving a profile version, including what it made stale."""

    version: ClientProfileVersionOut
    newly_stale_artifact_version_ids: list[uuid.UUID]


class PlaybookApprovalOut(BaseModel):
    """Result of approving a playbook version, including what it made stale."""

    version: PlaybookVersionOut
    newly_stale_artifact_version_ids: list[uuid.UUID]


class ArtifactVersionCreate(BaseModel):
    """Body for a new artifact version; inputs must be the current approved ones."""

    client_profile_version_id: uuid.UUID
    playbook_version_id: uuid.UUID | None = None
    data: dict = Field(default_factory=dict)


class ArtifactCreate(ArtifactVersionCreate):
    """Body for creating a new artifact (and its first version)."""

    client_id: uuid.UUID
    kind: str = Field(min_length=1, max_length=50)


class ArtifactVersionOut(BaseModel):
    """One version of an artifact, with provenance and staleness info."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    artifact_id: uuid.UUID
    version_number: int
    status: ReviewStatus
    data: dict
    client_profile_version_id: uuid.UUID
    playbook_version_id: uuid.UUID | None
    created_at: datetime
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    stale_at: datetime | None = None
    stale_reason: str | None = None
