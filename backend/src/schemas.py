"""Pydantic models that define the JSON shape of API requests and responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
    uploaded_at: datetime


class ExtractedTextOut(BaseModel):
    """Saved plain text returned after extraction or a text lookup."""

    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    text: str
    extracted_at: datetime
