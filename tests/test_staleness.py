"""Staleness behaviour end to end through the HTTP API.

Arrange with the factories (profile_factory, playbook_factory, client_factory);
act through the real endpoints via `api`.
"""

import uuid
from datetime import datetime, timezone

from src.models import ArtifactVersion, ClientProfileVersion, ReviewStatus
from src.staleness import is_artifact_stale, mark_stale_for_client_profile


def status_of(api, artifact_id, idx=-1):
    return api.history(artifact_id)[idx]["status"]


# --- creating artifacts --------------------------------------------------------


def test_artifact_requires_approved_profile_version(api, demo_client, profile_factory):
    v1 = profile_factory()  # draft
    r = api.artifact(demo_client.id, v1.id)
    assert r.status_code == 409
    assert "not approved" in r.json()["detail"]


def test_artifact_created_from_approved_profile_is_pinned_draft(
    api, demo_client, profile_factory
):
    v1 = profile_factory(approved=True)
    r = api.artifact(demo_client.id, v1.id)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "draft"
    assert body["version_number"] == 1
    assert body["client_profile_version_id"] == str(v1.id)
    assert body["stale_at"] is None


def test_artifact_cannot_use_another_clients_profile(
    api, profile_factory, client_factory
):
    """Cross-client isolation: same 404 as a nonexistent version."""
    v_a = profile_factory(approved=True)  # belongs to demo_client
    client_b = client_factory("B")
    assert api.artifact(client_b.id, v_a.id).status_code == 404


def test_artifact_rejects_superseded_profile_version(api, demo_client, profile_factory):
    v1 = profile_factory(approved=True)
    v2 = api.new_profile_version(v1.client_profile_id)
    assert api.approve_profile(v1.client_profile_id, v2["id"]).status_code == 200
    r = api.artifact(demo_client.id, v1.id)
    assert r.status_code == 409
    assert "superseded" in r.json()["detail"]


def test_artifact_unknown_client_and_version(api, demo_client):
    assert api.artifact(uuid.uuid4(), uuid.uuid4()).status_code == 404
    assert api.artifact(demo_client.id, uuid.uuid4()).status_code == 404


# --- the core feature: marking stale -------------------------------------------


def test_new_approved_profile_version_marks_artifact_stale(
    api, demo_client, profile_factory
):
    v1 = profile_factory(approved=True)
    pid = v1.client_profile_id
    art = api.artifact(demo_client.id, v1.id).json()

    # A draft correction alone must NOT make anything stale.
    v2 = api.new_profile_version(pid, {"budget": 9000})
    assert status_of(api, art["artifact_id"]) == "draft"
    assert api.stale() == []

    r = api.approve_profile(pid, v2["id"])
    assert r.status_code == 200
    assert r.json()["newly_stale_artifact_version_ids"] == [art["id"]]

    hist = api.history(art["artifact_id"])
    assert hist[0]["status"] == "stale"
    assert hist[0]["stale_at"] is not None
    assert "older version" in hist[0]["stale_reason"]
    assert [s["id"] for s in api.stale()] == [art["id"]]


def test_stale_keeps_approval_history(api, demo_client, profile_factory):
    """'Kept in history': an approved artifact that goes stale still shows it WAS approved."""
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    assert api.approve_artifact(art["artifact_id"], art["id"]).status_code == 200

    v2 = api.new_profile_version(v1.client_profile_id)
    api.approve_profile(v1.client_profile_id, v2["id"])

    h = api.history(art["artifact_id"])[0]
    assert h["status"] == "stale"
    assert h["approved_at"] is not None
    assert h["approved_by"] == api.reviewer
    assert h["data"] == {"headline": "hello"}


def test_unrelated_clients_artifacts_not_marked_stale(
    api, demo_client, client_factory, profile_factory
):
    client_b = client_factory("B")
    va = profile_factory(demo_client, approved=True)
    vb = profile_factory(client_b, approved=True)
    art_a = api.artifact(demo_client.id, va.id).json()
    art_b = api.artifact(client_b.id, vb.id).json()

    v2 = api.new_profile_version(va.client_profile_id)
    api.approve_profile(va.client_profile_id, v2["id"])

    assert status_of(api, art_a["artifact_id"]) == "stale"
    assert status_of(api, art_b["artifact_id"]) == "draft"
    assert [s["id"] for s in api.stale(demo_client.id)] == [art_a["id"]]
    assert api.stale(client_b.id) == []


def test_late_approval_of_older_version_does_not_roll_back(
    client, api, demo_client, profile_factory
):
    """Latest = highest version_number, not most recently approved."""
    v1 = profile_factory(approved=True)
    pid = v1.client_profile_id
    v2 = api.new_profile_version(pid)
    v3 = api.new_profile_version(pid)

    api.approve_profile(pid, v3["id"])
    art = api.artifact(demo_client.id, v3["id"]).json()

    # The reviewer gets around to approving v2 afterwards.
    r = api.approve_profile(pid, v2["id"])
    assert r.status_code == 200
    assert r.json()["newly_stale_artifact_version_ids"] == []
    assert status_of(api, art["artifact_id"]) == "draft"

    latest = client.get(f"/client-profiles/{pid}/latest-approved").json()
    assert latest["id"] == v3["id"]


def test_playbook_change_marks_dependent_artifacts_only(
    api, demo_client, profile_factory, playbook_factory
):
    pv = profile_factory(approved=True)
    pb1 = playbook_factory(approved=True)
    with_pb = api.artifact(demo_client.id, pv.id, pb1.id).json()
    without_pb = api.artifact(demo_client.id, pv.id, kind="message").json()

    pb2 = api.new_playbook_version(pb1.playbook_id)
    r = api.approve_playbook(pb1.playbook_id, pb2["id"])
    assert r.status_code == 200
    assert r.json()["newly_stale_artifact_version_ids"] == [with_pb["id"]]

    assert status_of(api, with_pb["artifact_id"]) == "stale"
    assert status_of(api, without_pb["artifact_id"]) == "draft"
    assert "Playbook" in api.history(with_pb["artifact_id"])[0]["stale_reason"]


def test_artifact_rejects_unapproved_or_superseded_playbook(
    api, demo_client, profile_factory, playbook_factory
):
    pv = profile_factory(approved=True)
    draft_pb = playbook_factory()
    assert api.artifact(demo_client.id, pv.id, draft_pb.id).status_code == 409

    pb1 = playbook_factory(approved=True)
    pb2 = api.new_playbook_version(pb1.playbook_id)
    api.approve_playbook(pb1.playbook_id, pb2["id"])
    assert api.artifact(demo_client.id, pv.id, pb1.id).status_code == 409
    assert api.artifact(demo_client.id, pv.id, uuid.uuid4()).status_code == 404


def test_marking_is_idempotent(db_session, api, demo_client, profile_factory):
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    v2 = api.new_profile_version(v1.client_profile_id)
    api.approve_profile(v1.client_profile_id, v2["id"])
    stamp = api.history(art["artifact_id"])[0]["stale_at"]

    assert mark_stale_for_client_profile(db_session, v1.client_profile_id) == []
    db_session.rollback()
    assert api.history(art["artifact_id"])[0]["stale_at"] == stamp


def test_rejected_artifacts_are_not_resurrected_as_stale(
    db_session, api, demo_client, profile_factory
):
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    av = db_session.get(ArtifactVersion, uuid.UUID(art["id"]))
    av.status = ReviewStatus.REJECTED
    db_session.commit()

    v2 = api.new_profile_version(v1.client_profile_id)
    r = api.approve_profile(v1.client_profile_id, v2["id"])
    assert r.json()["newly_stale_artifact_version_ids"] == []
    assert status_of(api, art["artifact_id"]) == "rejected"


# --- re-review flow ------------------------------------------------------------


def test_regenerating_clears_stale_queue_but_keeps_history(
    api, demo_client, profile_factory
):
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    v2 = api.new_profile_version(v1.client_profile_id)
    api.approve_profile(v1.client_profile_id, v2["id"])
    assert len(api.stale()) == 1

    # Can't rebuild from the old version...
    assert api.new_artifact_version(art["artifact_id"], v1.id).status_code == 409
    # ...but can from the current one.
    r = api.new_artifact_version(art["artifact_id"], v2["id"])
    assert r.status_code == 201
    assert r.json()["version_number"] == 2
    assert r.json()["status"] == "draft"

    assert api.stale() == []
    assert [h["status"] for h in api.history(art["artifact_id"])] == ["stale", "draft"]


def test_cannot_approve_a_version_already_marked_stale(
    api, demo_client, profile_factory
):
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    v2 = api.new_profile_version(v1.client_profile_id)
    api.approve_profile(v1.client_profile_id, v2["id"])

    r = api.approve_artifact(art["artifact_id"], art["id"])
    assert r.status_code == 409
    assert "stale" in r.json()["detail"]


def test_approve_rechecks_inputs_even_if_status_not_yet_stale(
    db_session, api, demo_client, profile_factory
):
    """Defence in depth: if marking was skipped, approve still refuses and flips it."""
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    v2 = api.new_profile_version(v1.client_profile_id)

    # Approve v2 directly in the DB, bypassing mark_stale_*.
    row = db_session.get(ClientProfileVersion, uuid.UUID(v2["id"]))
    row.status = ReviewStatus.APPROVED
    row.approved_at = datetime.now(timezone.utc)
    db_session.commit()
    assert status_of(api, art["artifact_id"]) == "draft"

    r = api.approve_artifact(art["artifact_id"], art["id"])
    assert r.status_code == 409
    h = api.history(art["artifact_id"])[0]
    assert h["status"] == "stale" and h["approved_at"] is None


def test_approve_current_artifact_succeeds_and_records_reviewer(
    api, demo_client, profile_factory
):
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    r = api.approve_artifact(art["artifact_id"], art["id"])
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == api.reviewer
    assert body["approved_at"] is not None
    assert api.approve_artifact(art["artifact_id"], art["id"]).status_code == 409


def test_approve_artifact_404s(api, demo_client, profile_factory):
    v1 = profile_factory(approved=True)
    art = api.artifact(demo_client.id, v1.id).json()
    other = api.artifact(demo_client.id, v1.id, kind="other").json()
    assert api.approve_artifact(uuid.uuid4(), art["id"]).status_code == 404
    assert api.approve_artifact(art["artifact_id"], uuid.uuid4()).status_code == 404
    assert api.approve_artifact(art["artifact_id"], other["id"]).status_code == 404


# --- is_artifact_stale directly ------------------------------------------------


def test_is_artifact_stale_profile(db_session, api, profile_factory):
    v1 = profile_factory(approved=True)
    assert is_artifact_stale(db_session, v1.id) is False
    assert is_artifact_stale(db_session, uuid.uuid4()) is True

    v2 = api.new_profile_version(v1.client_profile_id)
    assert is_artifact_stale(db_session, v1.id) is False
    api.approve_profile(v1.client_profile_id, v2["id"])
    assert is_artifact_stale(db_session, v1.id) is True
    assert is_artifact_stale(db_session, uuid.UUID(v2["id"])) is False


def test_is_artifact_stale_playbook(db_session, api, profile_factory, playbook_factory):
    pv = profile_factory(approved=True)
    pb1 = playbook_factory(approved=True)
    assert is_artifact_stale(db_session, pv.id, pb1.id) is False
    assert is_artifact_stale(db_session, pv.id, uuid.uuid4()) is True

    pb2 = api.new_playbook_version(pb1.playbook_id)
    api.approve_playbook(pb1.playbook_id, pb2["id"])
    assert is_artifact_stale(db_session, pv.id, pb1.id) is True
    assert is_artifact_stale(db_session, pv.id, uuid.UUID(pb2["id"])) is False
