"""#62 Approve: an open draft becomes a new approved profile version."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text

from src.db import SessionLocal
from src.models import ClientProfileVersion, ReviewStatus, Role
from src.routers import reviews

DRAFT = {
    "name": "Maya Chen",
    "email": None,
    "needs": ["More bookings"],
    "goals": ["Fill winter"],
    "source_references": [
        {"field": "name", "document_id": "intake", "quote": "Maya Chen"}
    ],
    "conflicts": [],
    "assessment": {"rules_version": 1, "missing_fields": ["email"]},
}


def url(version, action="approve", *, profile_id=None, version_id=None):
    return (
        f"/api/v1/reviews/profiles/{profile_id or version.client_profile_id}"
        f"/versions/{version_id or version.id}/{action}"
    )


def versions(db, profile_id):
    db.expire_all()
    return db.scalars(
        select(ClientProfileVersion)
        .where(ClientProfileVersion.client_profile_id == profile_id)
        .order_by(ClientProfileVersion.version_number)
    ).all()


@pytest.fixture
def draft(db_session, profile_factory):
    """A generated draft (v2) on top of the empty v1 placeholder."""
    placeholder = profile_factory()
    version = ClientProfileVersion(
        client_profile_id=placeholder.client_profile_id,
        version_number=2,
        status=ReviewStatus.IN_REVIEW,
        data=deepcopy(DRAFT),
    )
    db_session.add(version)
    db_session.commit()
    return version


@pytest.fixture
def reviewer(sign_in):
    return sign_in(Role.REVIEWER)


def test_approve_saves_draft_as_new_approved_version(db_session, draft, reviewer):
    http, user = reviewer

    response = http.post(url(draft))

    assert response.status_code == 201, response.text
    approved = response.json()["version"]
    assert approved["version_number"] == 3
    assert approved["status"] == "approved"
    assert approved["data"] == DRAFT
    assert approved["approved_by"] == str(user.id)
    assert approved["approved_at"] is not None
    rows = versions(db_session, draft.client_profile_id)
    assert [v.version_number for v in rows] == [1, 2, 3]
    # The draft itself is not rewritten; the new head carries the approval.
    assert rows[1].status == ReviewStatus.IN_REVIEW and rows[1].approved_at is None
    latest = http.get(
        f"/api/v1/client-profiles/{draft.client_profile_id}/latest-approved"
    )
    assert latest.json()["id"] == approved["id"]
    assert http.get("/api/v1/reviews").json() == []


def test_approve_takes_the_edited_draft(db_session, draft, reviewer):
    http, _ = reviewer
    edited = http.post(url(draft, "edits"), json={"changes": {"email": "m@x.test"}})
    assert edited.status_code == 201
    edited_version = db_session.get(
        ClientProfileVersion, uuid.UUID(edited.json()["id"])
    )

    response = http.post(url(edited_version))

    assert response.status_code == 201
    assert response.json()["version"]["data"]["email"] == "m@x.test"
    # Approving the pre-edit version is refused: it is no longer the head.
    assert http.post(url(draft)).status_code == 409


def test_repeated_approve_is_409_and_creates_one_approved_version(
    db_session, draft, reviewer
):
    http, _ = reviewer

    first = http.post(url(draft))
    second = http.post(url(draft))

    assert first.status_code == 201
    assert second.status_code == 409
    approved = [
        v for v in versions(db_session, draft.client_profile_id) if v.approved_at
    ]
    assert len(approved) == 1


@pytest.mark.parametrize("decided", [ReviewStatus.REJECTED, ReviewStatus.STALE])
def test_decided_draft_cannot_be_approved(db_session, draft, reviewer, decided):
    draft.status = decided
    db_session.commit()

    assert reviewer[0].post(url(draft)).status_code == 409
    assert len(versions(db_session, draft.client_profile_id)) == 2


def test_rejected_through_the_api_cannot_be_approved(db_session, draft, reviewer):
    http, user = reviewer
    rejected = http.post(url(draft, "reject"), json={"reason": "Wrong client"})
    assert rejected.json()["rejected_by"] == str(user.id)

    assert http.post(url(draft)).status_code == 409


def test_empty_placeholder_cannot_be_approved(db_session, profile_factory, reviewer):
    placeholder = profile_factory()

    response = reviewer[0].post(url(placeholder))

    assert response.status_code == 422
    assert len(versions(db_session, placeholder.client_profile_id)) == 1


def test_unknown_or_mismatched_version_is_404(draft, reviewer):
    http, _ = reviewer
    assert http.post(url(draft, version_id=uuid.uuid4())).status_code == 404
    assert http.post(url(draft, profile_id=uuid.uuid4())).status_code == 404


def test_admin_can_approve(draft, sign_in):
    assert sign_in(Role.ADMIN)[0].post(url(draft)).status_code == 201


@pytest.mark.parametrize("action", ["approve", "reject", "edits"])
def test_changing_a_draft_needs_a_signed_in_reviewer(
    db_session, client, draft, sign_in, action
):
    body = {
        "approve": None,
        "reject": {"reason": "Wrong"},
        "edits": {"changes": {"name": "X"}},
    }[action]
    viewer, _ = sign_in(Role.VIEWER)
    no_csrf, _ = sign_in(Role.REVIEWER)
    del no_csrf.headers["X-CSRF-Token"]

    assert client.post(url(draft, action), json=body).status_code == 401
    assert viewer.post(url(draft, action), json=body).status_code == 403
    assert no_csrf.post(url(draft, action), json=body).status_code == 403
    rows = versions(db_session, draft.client_profile_id)
    assert len(rows) == 2 and rows[1].status == ReviewStatus.IN_REVIEW


def test_approve_marks_artifacts_from_older_versions_stale(
    db_session, demo_client, draft, reviewer
):
    http, _ = reviewer
    # Make the draft profile's v1 approved and build an artifact from it.
    v1 = versions(db_session, draft.client_profile_id)[0]
    v1.status = ReviewStatus.APPROVED
    v1.approved_at = draft.created_at
    db_session.commit()
    artifact = http.post(
        "/api/v1/artifacts",
        json={
            "client_id": str(demo_client.id),
            "kind": "campaign_brief",
            "client_profile_version_id": str(v1.id),
            "playbook_version_id": None,
            "data": {"headline": "hello"},
        },
    )
    assert artifact.status_code == 201, artifact.text

    response = http.post(url(draft))

    assert response.status_code == 201
    assert response.json()["newly_stale_artifact_version_ids"] == [
        artifact.json()["id"]
    ]


def test_simultaneous_approvals_have_one_winner(db_session, draft, reviewer):
    # Plain values only: the threads must not touch the test's own session.
    approver = SimpleNamespace(id=reviewer[1].id)
    profile_id, version_id = draft.client_profile_id, draft.id
    barrier = Barrier(2)

    def approve(_):
        with SessionLocal() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            try:
                reviews.approve_draft(profile_id, version_id, db, approver)
                return 201
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(approve, range(2)))

    assert results == [201, 409]
    approved = [v for v in versions(db_session, profile_id) if v.approved_at]
    assert len(approved) == 1
