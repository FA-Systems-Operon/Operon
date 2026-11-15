"""#64 Rejection persists its state and reason without approving a profile."""

import uuid

import pytest
from tests.test_review_approve import versions

from src.models import ClientProfileVersion, ReviewStatus

DRAFT = {"name": "Maya Chen", "needs": ["More bookings"], "goals": ["Fill winter"]}


@pytest.fixture
def client(reviewer_client):
    """Changing a draft needs a signed-in reviewer (#62)."""
    return reviewer_client


def reject_url(version, *, profile_id=None, version_id=None):
    return (
        f"/api/v1/reviews/profiles/{profile_id or version.client_profile_id}"
        f"/versions/{version_id or version.id}/reject"
    )


@pytest.fixture
def draft(db_session, profile_factory):
    placeholder = profile_factory()
    version = ClientProfileVersion(
        client_profile_id=placeholder.client_profile_id,
        version_number=2,
        status=ReviewStatus.IN_REVIEW,
        data=DRAFT,
    )
    db_session.add(version)
    db_session.commit()
    return version


def test_reject_marks_draft_rejected_with_reason_and_no_new_version(
    client, db_session, draft
):
    before = {v.id for v in versions(db_session, draft.client_profile_id)}
    response = client.post(reject_url(draft), json={"reason": "  Wrong client  "})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(draft.id)
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "Wrong client"
    assert body["rejected_at"] is not None
    assert body["approved_at"] is None

    rows = versions(db_session, draft.client_profile_id)
    assert {v.id for v in rows} == before
    stored = next(v for v in rows if v.id == draft.id)
    assert stored.status == ReviewStatus.REJECTED
    assert stored.rejection_reason == "Wrong client"
    assert stored.rejected_at is not None
    assert all(v.status != ReviewStatus.APPROVED for v in rows)
    assert all(v.approved_by is None and v.approved_at is None for v in rows)

    reloaded = client.get(reject_url(draft).removesuffix("/reject"))
    assert reloaded.status_code == 200, reloaded.text
    saved = reloaded.json()["version"]
    assert saved["id"] == body["id"]
    assert saved["status"] == "rejected"
    assert saved["rejection_reason"] == "Wrong client"
    assert saved["rejected_at"] == body["rejected_at"]
    assert saved["approved_by"] is None
    assert saved["approved_at"] is None
    latest = client.get(
        f"/api/v1/client-profiles/{draft.client_profile_id}/latest-approved"
    )
    assert latest.status_code == 404
    # A rejected draft leaves the inbox.
    assert client.get("/api/v1/reviews").json() == []


@pytest.mark.parametrize("reason", ["", "   ", "x" * 501])
def test_reject_requires_short_nonblank_reason(client, db_session, draft, reason):
    response = client.post(reject_url(draft), json={"reason": reason})

    assert response.status_code == 422
    db_session.refresh(draft)
    assert draft.status == ReviewStatus.IN_REVIEW
    assert draft.rejection_reason is None


def test_reject_without_reason_is_422(client, draft):
    assert client.post(reject_url(draft), json={}).status_code == 422


def test_rejected_draft_cannot_be_rejected_again_or_approved(client, draft):
    assert client.post(reject_url(draft), json={"reason": "Wrong"}).status_code == 200

    again = client.post(reject_url(draft), json={"reason": "Twice"})
    approve = client.post(
        f"/api/v1/client-profiles/{draft.client_profile_id}/versions/{draft.id}/approve",
        json={"approved_by": str(uuid.uuid4())},
    )

    assert again.status_code == 409
    assert approve.status_code == 409
    reloaded = client.get(reject_url(draft).removesuffix("/reject")).json()
    assert reloaded["version"]["rejection_reason"] == "Wrong"
    assert reloaded["version"]["approved_at"] is None


def test_superseded_draft_cannot_be_rejected(client, db_session, draft):
    db_session.add(
        ClientProfileVersion(
            client_profile_id=draft.client_profile_id, version_number=3, data=DRAFT
        )
    )
    db_session.commit()

    assert client.post(reject_url(draft), json={"reason": "Old"}).status_code == 409


def test_unknown_or_mismatched_version_is_404(client, draft):
    assert (
        client.post(
            reject_url(draft, version_id=uuid.uuid4()), json={"reason": "x"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            reject_url(draft, profile_id=uuid.uuid4()), json={"reason": "x"}
        ).status_code
        == 404
    )
