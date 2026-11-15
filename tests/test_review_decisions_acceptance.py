"""AT 4.3 (#67): approve saved edits as a new version, or reject with a reason.

Reuse the generated-draft setup from AT 4.1 and the #62/#64 request/query helpers.
The two frontend scenarios use the same response fixture; persistence is checked
here against PostgreSQL, with the existing fake model and a signed-in reviewer.
"""

import uuid
from copy import deepcopy

import pytest
from tests.test_review_approve import url, versions
from tests.test_review_inbox_acceptance import (
    FIXTURE,
    fake_model,
    generate_draft,
    open_draft,
    open_inbox,
)
from tests.test_review_reject import reject_url

from src.models import ClientProfileVersion, ReviewStatus

DECISIONS = FIXTURE["review_decisions"]
pytestmark = pytest.mark.usefixtures(fake_model.__name__)


def test_approve_creates_a_new_approved_version_with_saved_content(
    client, reviewer_client, client_factory, db_session
):
    generate_draft(client, client_factory("Plateau Basements"))
    [item] = open_inbox(reviewer_client)
    original = open_draft(reviewer_client, item)["version"]
    draft = db_session.get(ClientProfileVersion, uuid.UUID(item["version_id"]))

    saved = reviewer_client.post(
        url(draft, "edits"), json={"changes": DECISIONS["changes"]}
    )
    assert saved.status_code == 201, saved.text
    edited = saved.json()
    expected = deepcopy(original["data"])
    expected["goals"][0] = DECISIONS["changes"]["goals/0"]
    assert edited["data"] == expected
    assert edited["version_number"] == DECISIONS["edited_version"]["version_number"]
    edited_row = db_session.get(ClientProfileVersion, uuid.UUID(edited["id"]))
    before = {v.id for v in versions(db_session, draft.client_profile_id)}

    response = reviewer_client.post(url(edited_row))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body.keys() == {"version", "newly_stale_artifact_version_ids"}
    approved = body["version"]
    assert approved.keys() == FIXTURE["draft"]["version"].keys()
    assert approved["status"] == DECISIONS["approved_version"]["status"]
    assert approved["version_number"] == DECISIONS["approved_version"]["version_number"]
    assert approved["id"] != edited["id"]
    assert approved["data"] == expected
    assert body["newly_stale_artifact_version_ids"] == []
    rows = versions(db_session, draft.client_profile_id)
    assert len(rows) == len(before) + 1
    [created] = [v for v in rows if v.id not in before]
    assert str(created.id) == approved["id"]
    assert created.status == ReviewStatus.APPROVED
    assert created.data == expected
    assert [v.id for v in rows if v.status == ReviewStatus.APPROVED] == [created.id]
    latest = reviewer_client.get(
        f"/api/v1/client-profiles/{draft.client_profile_id}/latest-approved"
    )
    assert latest.status_code == 200, latest.text
    assert latest.json() == approved


def test_reject_saves_the_reason_and_rejected_draft_without_an_approved_version(
    client, reviewer_client, client_factory, db_session
):
    generate_draft(client, client_factory("Plateau Basements"))
    [item] = open_inbox(reviewer_client)
    draft = db_session.get(ClientProfileVersion, uuid.UUID(item["version_id"]))
    before = {v.id for v in versions(db_session, draft.client_profile_id)}
    reason = DECISIONS["rejected_version"]["rejection_reason"]

    response = reviewer_client.post(reject_url(draft), json={"reason": reason})

    assert response.status_code == 200, response.text
    rejected = open_draft(reviewer_client, item)["version"]
    assert rejected == response.json()
    assert rejected.keys() == FIXTURE["draft"]["version"].keys()
    assert rejected["id"] == item["version_id"]
    assert rejected["status"] == DECISIONS["rejected_version"]["status"]
    assert rejected["rejection_reason"] == reason
    rows = versions(db_session, draft.client_profile_id)
    assert {v.id for v in rows} == before
    stored = db_session.get(ClientProfileVersion, draft.id)
    assert stored.status == ReviewStatus.REJECTED
    assert stored.rejection_reason == reason
    assert all(v.status != ReviewStatus.APPROVED for v in rows)
    assert all(v.approved_by is None and v.approved_at is None for v in rows)
    latest = reviewer_client.get(
        f"/api/v1/client-profiles/{draft.client_profile_id}/latest-approved"
    )
    assert latest.status_code == 404
