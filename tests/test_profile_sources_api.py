"""Save/retrieve source-linked drafts via the profile API (#40)."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from tests.test_profile_sources import add_text, make_draft

from src.models import ClientProfileVersion


def test_api_persists_and_returns_source_draft(
    client, db_session, profile_factory, stored_document
):
    original = profile_factory()
    document = stored_document()
    add_text(db_session, document)
    payload = make_draft(document.id).model_dump()
    url = f"/client-profiles/{original.client_profile_id}"
    response = client.post(f"{url}/source-drafts", json=payload)
    assert response.status_code == 201
    assert response.json()["data"] == payload
    assert response.json()["status"] == "draft"
    assert response.json()["version_number"] == 2
    assert client.get(f"{url}/versions").json()[-1] == response.json()


@pytest.mark.parametrize(
    "case",
    [
        "unknown_document",
        "wrong_client",
        "bad_quote",
        "missing_reference",
        "invalid_id",
    ],
)
def test_api_rejects_invalid_evidence_without_saving(
    client, db_session, profile_factory, stored_document, client_factory, case
):
    original = profile_factory()
    owner = client_factory("Other") if case == "wrong_client" else None
    document = stored_document(owner=owner)
    add_text(db_session, document)
    payload = make_draft(document.id).model_dump()
    if case == "unknown_document":
        payload["source_references"][0]["document_id"] = str(uuid.uuid4())
    elif case == "invalid_id":
        payload["source_references"][0]["document_id"] = "not-a-uuid"
    elif case == "bad_quote":
        payload["source_references"][0]["quote"] = "Invented"
    elif case == "missing_reference":
        payload["source_references"] = []
    response = client.post(
        f"/client-profiles/{original.client_profile_id}/source-drafts", json=payload
    )
    assert response.status_code == 422
    assert (
        db_session.scalar(select(func.count()).select_from(ClientProfileVersion)) == 1
    )


def test_api_returns_404_for_missing_profile(client):
    payload = {"name": None, "needs": [], "goals": [], "source_references": []}
    response = client.post(
        f"/client-profiles/{uuid.uuid4()}/source-drafts", json=payload
    )
    assert response.status_code == 404


def test_database_failure_rolls_back_draft(
    client, db_session, profile_factory, stored_document
):
    original = profile_factory()
    document = stored_document()
    add_text(db_session, document)
    with (
        patch.object(db_session, "commit", side_effect=SQLAlchemyError("offline")),
        pytest.raises(SQLAlchemyError),
    ):
        client.post(
            f"/client-profiles/{original.client_profile_id}/source-drafts",
            json=make_draft(document.id).model_dump(),
        )
    assert (
        db_session.scalar(select(func.count()).select_from(ClientProfileVersion)) == 1
    )
