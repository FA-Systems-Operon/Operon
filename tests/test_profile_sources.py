"""Source evidence persists with each draft and stays scoped to its client (#40)."""

import uuid

import pytest
from sqlalchemy import func, select

from src.ai.source_prompt import SourceLinkedProfile
from src.models import ClientProfileVersion, ExtractedText, ReviewStatus
from src.profile_sources import save_source_profile


def make_draft(document_id, quote="Alice"):
    return SourceLinkedProfile.model_validate(
        {
            "name": "Alice",
            "needs": [],
            "goals": [],
            "source_references": [
                {"field": "name", "document_id": str(document_id), "quote": quote}
            ],
        }
    )


def add_text(db, document):
    db.add(ExtractedText(document_id=document.id, text="Alice: Hello."))
    db.commit()


def test_draft_round_trip_preserves_evidence_and_old_version(
    db_session, profile_factory, stored_document, client
):
    original = profile_factory(approved=True, data={"name": "Old"})
    document = stored_document()
    add_text(db_session, document)
    draft = make_draft(document.id)
    version = save_source_profile(db_session, original.client_profile_id, draft)
    db_session.commit()
    db_session.expire_all()
    assert version.status == ReviewStatus.DRAFT
    assert version.version_number == 2
    assert version.data == draft.model_dump()
    assert original.data == {"name": "Old"}
    response = client.get(f"/client-profiles/{original.client_profile_id}/versions")
    assert response.status_code == 200
    assert response.json()[-1]["data"] == draft.model_dump()
    approved = client.get(
        f"/client-profiles/{original.client_profile_id}/latest-approved"
    )
    assert approved.json()["id"] == str(original.id)


@pytest.mark.parametrize(
    "failure", ["other_client", "missing_text", "bad_quote", "unknown"]
)
def test_invalid_sources_do_not_create_a_version(
    db_session, profile_factory, stored_document, client_factory, failure
):
    original = profile_factory()
    owner = client_factory("Other") if failure == "other_client" else None
    document = (
        stored_document(owner=owner) if failure == "other_client" else stored_document()
    )
    if failure != "missing_text":
        add_text(db_session, document)
    draft = make_draft(
        uuid.uuid4() if failure == "unknown" else document.id,
        "Invented" if failure == "bad_quote" else "Alice",
    )
    with pytest.raises(ValueError):
        save_source_profile(db_session, original.client_profile_id, draft)
    db_session.rollback()
    assert (
        db_session.scalar(select(func.count()).select_from(ClientProfileVersion)) == 1
    )


def test_missing_profile_does_not_create_a_version(db_session):
    with pytest.raises(LookupError, match="not found"):
        save_source_profile(db_session, uuid.uuid4(), make_draft(uuid.uuid4()))
    db_session.rollback()


def test_save_participates_in_callers_transaction(
    db_session, profile_factory, stored_document
):
    original = profile_factory()
    document = stored_document()
    add_text(db_session, document)
    save_source_profile(db_session, original.client_profile_id, make_draft(document.id))
    db_session.rollback()
    assert (
        db_session.scalar(select(func.count()).select_from(ClientProfileVersion)) == 1
    )
