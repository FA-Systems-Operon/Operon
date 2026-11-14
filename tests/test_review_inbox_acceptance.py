"""AT 4.1 (#65): Given a draft exists awaiting review, when a reviewer opens the
review inbox, then it appears in the list showing the client name and generation
time. Given a reviewer selects a draft from the list, when the detail view opens,
then it shows the evidence and proposed profile fields side by side.

Drafts are made the way the app makes them: both files uploaded through the API,
then the onboarding job drafts them with a faked model, so CI needs no Ollama.
The reviewer side is frontend/src/pages/ReviewInbox.acceptance.test.tsx. Its API
replies come from tests/fixtures/review_inbox/responses.json, and the shape test
here fails if the real responses stop matching that file.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
from tests.test_onboarding_jobs import (
    INTAKE,
    TRANSCRIPT,
    SourceAwareProvider,
    combined_draft,
    get_job,
    start,
    upload_pair,
)

INBOX = "/api/v1/reviews"
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/review_inbox/responses.json").read_text("utf-8")
)
SOURCE_TEXT = {"transcript": TRANSCRIPT, "intake": INTAKE}


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    model = SourceAwareProvider(combined_draft)
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: model)


def generate_draft(client, owner):
    """Upload both files and let the onboarding job draft them, as the app does."""
    transcript, intake = upload_pair(client, owner)
    started = start(client, owner, transcript, intake)
    assert started.status_code == 201, started.text
    job = get_job(client, owner, started.json())
    assert job["status"] == "succeeded", job["error"]
    return job


def open_inbox(client):
    response = client.get(INBOX)
    assert response.status_code == 200, response.text
    return response.json()


def open_draft(client, item):
    """Open an inbox item using only the IDs the inbox returned."""
    profile_id, version_id = item["client_profile_id"], item["version_id"]
    response = client.get(f"{INBOX}/profiles/{profile_id}/versions/{version_id}")
    assert response.status_code == 200, response.text
    return response.json()


def evidence(draft):
    """Each reference as (field, kind of the cited document, quote)."""
    kinds = {document["id"]: document["kind"] for document in draft["documents"]}
    return [
        (ref["field"], kinds[ref["document_id"]], ref["quote"])
        for ref in draft["version"]["data"]["source_references"]
    ]


def test_inbox_lists_the_awaiting_draft_with_client_name_and_time(
    client, client_factory, reviewer_client
):
    awaiting = client_factory("Plateau Basements")
    job = generate_draft(client, awaiting)
    generate_draft(client, client_factory("Acme Plumbing"))
    [acme] = [
        item
        for item in open_inbox(client)
        if item["client_name"] != "Plateau Basements"
    ]
    approved = reviewer_client.post(
        f"/api/v1/client-profiles/{acme['client_profile_id']}/versions/{acme['version_id']}/approve",
    )
    assert approved.status_code == 200, approved.text
    northshore = client_factory("Northshore Kitchens")
    placeholder = client.post(
        "/api/v1/client-profiles", params={"client_id": str(northshore.id)}
    )
    assert placeholder.status_code == 201, placeholder.text

    [item] = open_inbox(client)

    assert item["client_name"] == "Plateau Basements"
    assert item["client_id"] == str(awaiting.id)
    assert item["version_id"] == job["result_version_id"]
    assert item["status"] == "draft"
    # The time shown is when the job saved the draft, not when the client was added.
    saved = open_draft(client, item)
    assert item["created_at"] == saved["version"]["created_at"]
    created = datetime.fromisoformat(saved["client"]["created_at"])
    assert datetime.fromisoformat(item["created_at"]) > created


def test_selected_draft_opens_with_its_fields_and_evidence(client, client_factory):
    owner = client_factory("Plateau Basements")
    generate_draft(client, owner)
    [item] = open_inbox(client)

    draft = open_draft(client, item)

    assert draft["client"]["name"] == "Plateau Basements"
    assert draft["version"]["id"] == item["version_id"]
    # The proposed fields, as the frontend fixture shows them.
    data, shown = draft["version"]["data"], FIXTURE["draft"]["version"]["data"]
    for field in ("name", "needs", "goals"):
        assert data[field] == shown[field]
    # The evidence: every quote cites one of the returned documents, and occurs
    # word for word in the file of that kind that was uploaded.
    assert sorted(document["kind"] for document in draft["documents"]) == [
        "intake",
        "transcript",
    ]
    for _, kind, quote in evidence(draft):
        assert quote in SOURCE_TEXT[kind]
    assert evidence(draft) == evidence(FIXTURE["draft"])


def test_frontend_fixture_has_the_real_response_shape(client, client_factory):
    generate_draft(client, client_factory("Plateau Basements"))
    [item] = open_inbox(client)
    draft, expected = open_draft(client, item), FIXTURE["draft"]

    assert item.keys() == FIXTURE["inbox_item"].keys()
    assert draft.keys() == expected.keys()
    assert draft["version"].keys() == expected["version"].keys()
    assert draft["client"].keys() == expected["client"].keys()
    assert draft["documents"][0].keys() == expected["documents"][0].keys()
    # The fixture leaves out the null onboarding fields; the rest are real keys.
    assert expected["version"]["data"].keys() <= draft["version"]["data"].keys()


def test_inbox_is_empty_when_no_draft_awaits_review(client, client_factory):
    # Files uploaded but no draft started yet.
    upload_pair(client, client_factory("Plateau Basements"))

    assert open_inbox(client) == []
