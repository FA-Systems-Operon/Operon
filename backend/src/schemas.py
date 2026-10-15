"""Pydantic models that define the JSON shape of API responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
