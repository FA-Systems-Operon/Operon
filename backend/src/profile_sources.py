"""Persist validated source-linked drafts as immutable profile versions (#40)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ai.source_prompt import SourceInput, SourceLinkedProfile, parse_source_profile
from src.models import (
    ClientProfile,
    ClientProfileVersion,
    ExtractedText,
    SourceDocument,
)
from src.versioning import next_client_profile_version


def save_source_profile(
    db: Session, profile_id: uuid.UUID, draft: SourceLinkedProfile
) -> ClientProfileVersion:
    """Validate against this client's stored text, then save values and evidence.

    References live in the existing JSON snapshot alongside name/needs/goals.
    A new version preserves the evidence of previous drafts. The caller owns
    commit/rollback so this can participate in a job's transaction.
    """
    profile = db.get(ClientProfile, profile_id, with_for_update=True)
    if profile is None:
        raise LookupError("Client profile not found")
    conflict_ids = {
        alternative.document_id
        for conflict in draft.conflicts
        for alternative in conflict.alternatives
    }
    document_ids = {
        reference.document_id for reference in draft.source_references
    } | conflict_ids
    try:
        ids = {uuid.UUID(document_id) for document_id in document_ids}
        conflict_uuids = {uuid.UUID(value) for value in conflict_ids}
    except ValueError as error:
        raise ValueError("References must identify stored source documents") from error
    # Canonicalize a copy: equivalent UUID spellings must match stored IDs,
    # and normalizing must not mutate the caller's generated draft.
    draft = draft.model_copy(
        update={
            "source_references": [
                reference.model_copy(
                    update={"document_id": str(uuid.UUID(reference.document_id))}
                )
                for reference in draft.source_references
            ],
            "conflicts": [
                conflict.model_copy(
                    update={
                        "alternatives": [
                            alternative.model_copy(
                                update={
                                    "document_id": str(
                                        uuid.UUID(alternative.document_id)
                                    )
                                }
                            )
                            for alternative in conflict.alternatives
                        ]
                    }
                )
                for conflict in draft.conflicts
            ],
        }
    )
    sources = []
    for document_id in ids:
        row = db.execute(
            select(SourceDocument, ExtractedText)
            .join(ExtractedText, ExtractedText.document_id == SourceDocument.id)
            .where(
                SourceDocument.id == document_id,
                SourceDocument.client_id == profile.client_id,
            )
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise ValueError("Source document or extracted text is unavailable")
        document, extracted = row
        if document.id in conflict_uuids and document.kind is None:
            raise ValueError("Conflict evidence requires stored document kinds")
        # Untyped historical documents still support ordinary quote references.
        sources.append(
            SourceInput(
                document_id=str(document.id),
                kind=document.kind.value if document.kind else "transcript",
                text=extracted.text,
            )
        )
    draft = parse_source_profile(draft.model_dump_json(), sources)
    version = ClientProfileVersion(
        client_profile_id=profile_id,
        version_number=next_client_profile_version(db, profile_id),
        data=draft.model_dump(),
    )
    db.add(version)
    db.flush()
    return version
