"""#60 save contract; #66 can reuse these API scenarios for acceptance."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.db import SessionLocal
from src.models import ClientProfile, ClientProfileVersion, ReviewStatus
from src.review_edits import save_review_edits
from src.routers import reviews
from src.schemas import ReviewEditsIn

DRAFT = {
    "name": "Maya Chen",
    "email": None,
    "needs": ["More bookings", "Less admin"],
    "goals": ["Fill winter"],
    "source_references": [
        {"field": "name", "document_id": "original-intake", "quote": "Maya Chen"}
    ],
    "conflicts": [
        {
            "field": "email",
            "explanation": "Sources disagree",
            "alternatives": [
                {"value": "call@example.test", "document_id": "call", "quote": "call"},
                {"value": "form@example.test", "document_id": "form", "quote": "form"},
            ],
        }
    ],
    "assessment": {"rules_version": 1, "missing_fields": ["website"]},
    "legacy": {"preserve": True},
}


def edits_url(version, *, profile_id=None, version_id=None):
    return (
        f"/api/v1/reviews/profiles/{profile_id or version.client_profile_id}"
        f"/versions/{version_id or version.id}/edits"
    )


def versions(db, profile_id):
    return db.scalars(
        select(ClientProfileVersion)
        .where(ClientProfileVersion.client_profile_id == profile_id)
        .order_by(ClientProfileVersion.version_number)
    ).all()


@pytest.mark.parametrize("status", [ReviewStatus.DRAFT, ReviewStatus.IN_REVIEW])
def test_save_appends_draft_and_reload_keeps_corrections_and_original_history(
    client, db_session, profile_factory, status
):
    base = profile_factory(data=deepcopy(DRAFT))
    base.status = status
    db_session.commit()
    original = deepcopy(base.data)
    changes = {
        "name": "  Corrected name  ",
        "email": "chosen@example.test",
        "website": None,
        "needs/1": "Less paperwork",
        "goals/0": "Fill spring",
    }
    response = client.post(edits_url(base), json={"changes": changes})
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["id"] != str(base.id)
    assert saved["version_number"] == 2
    assert saved["status"] == status.value
    assert saved["approved_at"] is None
    assert saved["approved_by"] is None
    assert saved["data"] == {
        **original,
        "name": "Corrected name",
        "email": "chosen@example.test",
        "website": None,
        "needs": ["More bookings", "Less paperwork"],
        "goals": ["Fill spring"],
        "assessment": None,
    }
    detail = client.get(
        f"/api/v1/reviews/profiles/{base.client_profile_id}/versions/{saved['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["version"] == saved
    db_session.refresh(base)
    assert base.data == original
    assert base.status == status
    assert len(versions(db_session, base.client_profile_id)) == 2


@pytest.mark.parametrize("value", [None, "", "   "])
def test_save_allows_clearing_nullable_scalars(client, profile_factory, value):
    base = profile_factory(data=deepcopy(DRAFT))
    response = client.post(edits_url(base), json={"changes": {"name": value}})
    assert response.status_code == 201
    assert response.json()["data"]["name"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "x"},
        {"assessment": None},
        {"conflicts": None},
        {"source_references": None},
        {"approved_at": "now"},
        {"status": "approved"},
        {"needs": "new list"},
        {"needs/01": "noncanonical"},
        {"needs/2": "new item"},
        {"needs/-1": "negative index"},
        {"needs/" + "9" * 100: "oversized index"},
        {"needs/0": None},
        {"goals/0": "   "},
        {"email": 123},
        {"name": True},
        {"email": ["not", "text"]},
    ],
)
def test_invalid_save_is_atomic(client, db_session, profile_factory, changes):
    base = profile_factory(data=deepcopy(DRAFT))
    # A valid correction before the invalid one must not leak into storage.
    body = {"changes": {"website": "example.test", **changes}}
    response = client.post(edits_url(base), json=body)
    assert response.status_code == 422, response.text
    db_session.refresh(base)
    assert base.data == DRAFT
    assert len(versions(db_session, base.client_profile_id)) == 1


def test_save_rejects_extra_request_metadata(client, profile_factory):
    base = profile_factory(data=deepcopy(DRAFT))
    response = client.post(
        edits_url(base),
        json={"changes": {"name": "Corrected"}, "approved_by": str(uuid.uuid4())},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("items", [None, "not a list", [42]])
def test_save_does_not_edit_malformed_legacy_list_items(client, profile_factory, items):
    base = profile_factory(data={**deepcopy(DRAFT), "needs": items})
    response = client.post(edits_url(base), json={"changes": {"needs/0": "Corrected"}})
    assert response.status_code == 422


@pytest.mark.parametrize("data", [[], ["legacy"], "legacy", 42, True, None])
def test_nonobject_base_data_returns_clean_422_without_writing(
    client, db_session, profile_factory, data
):
    profile = profile_factory()
    base = ClientProfileVersion(
        client_profile_id=profile.client_profile_id, version_number=2, data=data
    )
    db_session.add(base)
    db_session.commit()
    response = client.post(edits_url(base), json={"changes": {"name": "Corrected"}})
    assert response.status_code == 422
    assert response.json() == {"detail": "Draft data must be a JSON object"}
    db_session.refresh(base)
    assert base.data == data
    assert len(versions(db_session, base.client_profile_id)) == 2


@pytest.mark.parametrize("changes", [{}, {"name": "Maya Chen"}])
def test_unchanged_retry_checks_freshness_without_creating_a_version(
    client, db_session, profile_factory, changes
):
    base = profile_factory(data=deepcopy(DRAFT))
    response = client.post(edits_url(base), json={"changes": changes})
    assert response.status_code == 200
    assert response.json()["id"] == str(base.id)
    assert response.json()["data"]["assessment"] == DRAFT["assessment"]
    assert len(versions(db_session, base.client_profile_id)) == 1


def test_save_from_superseded_version_returns_409_without_writing(
    client, db_session, profile_factory, api
):
    base = profile_factory(data=deepcopy(DRAFT))
    newer = api.new_profile_version(
        base.client_profile_id, {"name": "Someone else's save"}
    )
    for changes in ({"name": "My correction"}, {}):
        response = client.post(edits_url(base), json={"changes": changes})
        assert response.status_code == 409
    assert len(versions(db_session, base.client_profile_id)) == 2
    assert versions(db_session, base.client_profile_id)[1].data == newer["data"]


@pytest.mark.parametrize(
    "status", [ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.STALE]
)
def test_decided_or_stale_version_cannot_be_saved(
    client, db_session, profile_factory, status
):
    base = profile_factory(data=deepcopy(DRAFT))
    base.status = status
    db_session.commit()
    response = client.post(edits_url(base), json={"changes": {"name": "Corrected"}})
    assert response.status_code == 409
    assert len(versions(db_session, base.client_profile_id)) == 1


@pytest.mark.parametrize("missing", ["profile", "version", "other_profile"])
def test_save_is_scoped_to_the_profile(client, profile_factory, missing):
    base = profile_factory(data=deepcopy(DRAFT))
    kwargs = (
        {"profile_id": uuid.uuid4()}
        if missing == "profile"
        else {"version_id": uuid.uuid4()}
    )
    if missing == "other_profile":
        kwargs = {"version_id": profile_factory().id}
    response = client.post(
        edits_url(base, **kwargs), json={"changes": {"name": "Corrected"}}
    )
    assert response.status_code == 404


@pytest.mark.parametrize("failure", ["flush", "commit"])
def test_storage_failure_rolls_back_the_entire_save(
    client, db_session, profile_factory, monkeypatch, failure
):
    base = profile_factory(data=deepcopy(DRAFT))

    def fail(*args, **kwargs):
        raise SQLAlchemyError("Simulated storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(db_session, failure, fail)
        with pytest.raises(SQLAlchemyError):
            client.post(edits_url(base), json={"changes": {"name": "Corrected"}})
    assert len(versions(db_session, base.client_profile_id)) == 1
    db_session.refresh(base)
    assert base.data == DRAFT


def test_simultaneous_saves_have_one_winner_and_one_stale_response(
    db_session, profile_factory
):
    base = profile_factory(data=deepcopy(DRAFT))
    profile_id, version_id = base.client_profile_id, base.id
    barrier = Barrier(2)

    def save(name):
        with SessionLocal() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            try:
                saved = reviews.save_draft_edits(
                    profile_id,
                    version_id,
                    ReviewEditsIn(changes={"name": name}),
                    db,
                    Response(),
                )
                return 201, saved.data["name"]
            except HTTPException as error:
                return error.status_code, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["Reviewer one", "Reviewer two"]))
    assert sorted(code for code, _ in results) == [201, 409]
    saved = versions(db_session, profile_id)
    assert len(saved) == 2
    assert saved[-1].data["name"] == next(name for code, name in results if code == 201)
    assert saved[0].data == DRAFT


def test_save_holds_parent_lock_until_the_transaction_finishes(
    db_session, profile_factory
):
    base = profile_factory(data=deepcopy(DRAFT))
    save_review_edits(
        db_session,
        base.client_profile_id,
        base.id,
        ReviewEditsIn(changes={"name": "Corrected"}),
    )
    with SessionLocal() as other:
        with pytest.raises(OperationalError) as failure:
            other.scalar(
                select(ClientProfile)
                .where(ClientProfile.id == base.client_profile_id)
                .with_for_update(nowait=True)
            )
        assert failure.value.orig.sqlstate == "55P03"  # lock_not_available
    db_session.rollback()
