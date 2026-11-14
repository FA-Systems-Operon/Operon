"""#43: required onboarding fields, conflict provenance and immutable persistence."""

import copy
import json
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from src.ai.source_prompt import SourceInput, SourceLinkedProfile, parse_source_profile
from src.models import ClientProfileVersion, DocumentKind, ExtractedText
from src.profile_flags import MANDATORY_FIELDS


def empty_profile():
    return {"name": None, "needs": [], "goals": [], "source_references": []}


@pytest.fixture
def conflict_case():
    sources = [
        SourceInput(
            document_id="call", kind="transcript", text="Email: sales@example.test"
        ),
        SourceInput(
            document_id="form", kind="intake", text="Email: hello@example.test"
        ),
    ]
    payload = {
        **empty_profile(),
        "conflicts": [
            {
                "field": "email",
                "explanation": "Different contact emails for the same business.",
                "alternatives": [
                    {
                        "value": "sales@example.test",
                        "document_id": "call",
                        "quote": sources[0].text,
                    },
                    {
                        "value": "hello@example.test",
                        "document_id": "form",
                        "quote": sources[1].text,
                    },
                ],
            }
        ],
    }
    return payload, sources


def test_missing_fields_are_exactly_the_nine_business_requirements():
    draft = parse_source_profile(json.dumps(empty_profile()), [])
    assert draft.assessment.missing_fields == list(MANDATORY_FIELDS)
    assert "name" not in draft.assessment.missing_fields
    # Client/model claims that the profile is complete are recomputed.
    payload = {
        **empty_profile(),
        "assessment": {"rules_version": 1, "missing_fields": []},
    }
    assert parse_source_profile(json.dumps(payload), []).assessment == draft.assessment


@pytest.mark.parametrize("field", MANDATORY_FIELDS)
def test_each_mandatory_field_can_be_backed_by_either_source(field):
    for kind in ("transcript", "intake"):
        source = SourceInput(document_id="doc", kind=kind, text="Recorded value")
        payload = {
            **empty_profile(),
            field: "Recorded value",
            "source_references": [
                {"field": field, "document_id": "doc", "quote": "Recorded value"}
            ],
        }
        draft = parse_source_profile(json.dumps(payload), [source])
        assert field not in draft.assessment.missing_fields
        assert len(draft.assessment.missing_fields) == 8
        payload["source_references"] = []
        with pytest.raises(ValueError, match="Missing source references"):
            parse_source_profile(json.dumps(payload), [source])


@pytest.mark.parametrize("field", MANDATORY_FIELDS)
def test_blank_onboarding_values_are_invalid(field):
    with pytest.raises(ValidationError):
        SourceLinkedProfile.model_validate({**empty_profile(), field: " \n "})


def test_conflict_preserves_alternatives_without_selecting_a_winner(conflict_case):
    payload, sources = conflict_case
    draft = parse_source_profile(json.dumps(payload), sources)
    assert draft.email is None
    assert "email" not in draft.assessment.missing_fields
    assert draft.conflicts[0].model_dump() == payload["conflicts"][0]


@pytest.mark.parametrize(
    "failure",
    [
        "unknown_document",
        "invented_quote",
        "same_document",
        "same_kind",
        "same_value",
        "duplicate",
        "absent_item",
        "malformed_path",
        "unknown_field",
        "blank_explanation",
        "chosen_winner",
        "only_one_alternative",
    ],
)
def test_invalid_conflicts_are_rejected(conflict_case, failure):
    payload, sources = conflict_case
    conflict = payload["conflicts"][0]
    if failure == "unknown_document":
        conflict["alternatives"][0]["document_id"] = "unknown"
    elif failure == "invented_quote":
        conflict["alternatives"][0]["quote"] = "Not in source"
    elif failure == "same_document":
        conflict["alternatives"][1].update(document_id="call", quote=sources[0].text)
    elif failure == "same_kind":
        sources[1] = sources[1].model_copy(update={"kind": "transcript"})
    elif failure == "same_value":
        conflict["alternatives"][1]["value"] = " SALES@example.test "
    elif failure == "duplicate":
        payload["conflicts"].append(copy.deepcopy(conflict))
    elif failure == "absent_item":
        conflict["field"] = "goals/0"
    elif failure == "malformed_path":
        conflict["field"] = "needs/01"
    elif failure == "unknown_field":
        conflict["field"] = "password"
    elif failure == "blank_explanation":
        conflict["explanation"] = " "
    elif failure == "chosen_winner":
        payload["email"] = "sales@example.test"
        payload["source_references"] = [
            {
                "field": "email",
                "document_id": "call",
                "quote": sources[0].text,
            }
        ]
    elif failure == "only_one_alternative":
        conflict["alternatives"].pop()
    with pytest.raises(ValueError):
        parse_source_profile(json.dumps(payload), sources)


def stored_conflict(db, stored_document, payload, sources, *, other_owner=None):
    payload = copy.deepcopy(payload)
    for index, source in enumerate(sources):
        document = stored_document(
            data=source.text.encode(), owner=other_owner if index else None
        )
        document.kind = DocumentKind(source.kind)
        db.add(ExtractedText(document_id=document.id, text=source.text))
        payload["conflicts"][0]["alternatives"][index]["document_id"] = str(document.id)
    db.commit()
    return payload


def test_api_saves_conflict_only_evidence_and_preserves_approved_history(
    client,
    db_session,
    profile_factory,
    stored_document,
    conflict_case,
):
    old = profile_factory(approved=True, data={"email": "historical@example.test"})
    payload = stored_conflict(db_session, stored_document, *conflict_case)
    # Alternate UUID spellings must be normalized without losing the evidence.
    alternative = payload["conflicts"][0]["alternatives"][0]
    alternative["document_id"] = uuid.UUID(alternative["document_id"]).hex
    url = f"/api/v1/client-profiles/{old.client_profile_id}"
    response = client.post(f"{url}/source-drafts", json=payload)
    assert response.status_code == 201, response.text
    saved = client.get(f"{url}/versions").json()[-1]
    assert saved["data"]["conflicts"][0]["alternatives"][0]["document_id"] == str(
        uuid.UUID(alternative["document_id"])
    )
    assert saved["status"] == "draft"
    assert "email" not in saved["data"]["assessment"]["missing_fields"]
    assert old.data == {"email": "historical@example.test"}
    assert client.get(f"{url}/latest-approved").json()["id"] == str(old.id)


@pytest.mark.parametrize("failure", ["other_client", "missing_kind", "bad_quote"])
def test_api_rejects_invalid_conflict_without_a_new_version(
    client,
    db_session,
    profile_factory,
    stored_document,
    client_factory,
    conflict_case,
    failure,
):
    old = profile_factory()
    payload = stored_conflict(
        db_session,
        stored_document,
        *conflict_case,
        other_owner=client_factory("Other") if failure == "other_client" else None,
    )
    if failure == "missing_kind":
        from src.models import SourceDocument

        document_id = payload["conflicts"][0]["alternatives"][1]["document_id"]
        db_session.get(SourceDocument, uuid.UUID(document_id)).kind = None
        db_session.commit()
    elif failure == "bad_quote":
        payload["conflicts"][0]["alternatives"][1]["quote"] = "Invented"
    response = client.post(
        f"/api/v1/client-profiles/{old.client_profile_id}/source-drafts", json=payload
    )
    assert response.status_code == 422
    assert (
        db_session.scalar(select(func.count()).select_from(ClientProfileVersion)) == 1
    )
