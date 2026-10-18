"""#21: exercise real approvals and persisted history for both source types."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from src.models import PlaybookVersion


@pytest.mark.parametrize("source_kind", ["profile", "playbook"])
def test_edit_approve_and_staleness_preserve_history(
    source_kind, client, api, demo_client, profile_factory, playbook_factory
):
    profile = profile_factory(data={"area": "Montreal"})
    playbook = playbook_factory(data={"rule": "Original rule"})
    assert api.approve_profile(profile.client_profile_id, profile.id).status_code == 200
    assert api.approve_playbook(playbook.playbook_id, playbook.id).status_code == 200
    if source_kind == "profile":
        parent_id, source_id = profile.client_profile_id, profile.id
        path, approve = "/client-profiles", api.approve_profile
    else:
        parent_id, source_id = playbook.playbook_id, playbook.id
        path, approve = "/playbooks", api.approve_playbook
    url = f"{path}/{parent_id}"
    original = client.get(f"{url}/latest-approved").json()
    artifact_response = api.artifact(demo_client.id, profile.id, playbook.id)
    assert artifact_response.status_code == 201
    artifact = artifact_response.json()
    approval = api.approve_artifact(artifact["artifact_id"], artifact["id"])
    assert approval.status_code == 200
    artifact_before = approval.json()

    edited = client.put(f"{url}", json={"changed": "Reviewed correction"})
    assert edited.status_code == 200
    draft = edited.json()
    assert draft["id"] != str(source_id)
    assert draft["version_number"] == 2
    assert draft["status"] == "draft"
    assert draft["approved_at"] is None
    assert draft["approved_by"] is None
    assert client.get(f"{url}/latest-approved").json() == original
    assert client.get(f"{url}/versions").json()[0] == original
    assert api.history(artifact["artifact_id"])[0] == artifact_before
    assert api.stale(demo_client.id) == []

    approved = approve(parent_id, draft["id"])
    assert approved.status_code == 200
    assert approved.json()["newly_stale_artifact_version_ids"] == [artifact["id"]]
    current = client.get(f"{url}/latest-approved").json()
    assert current["id"] == draft["id"]
    assert current["status"] == "approved"
    assert current["data"] == draft["data"]
    assert current["approved_by"] == api.reviewer
    # The old source remains approved history; only the dependent artifact is stale.
    assert client.get(f"{url}/versions").json()[0] == original
    stale = api.history(artifact["artifact_id"])[0]
    assert stale["status"] == "stale"
    assert stale["stale_at"] is not None
    assert stale["stale_reason"]
    for key in (
        "id",
        "data",
        "approved_at",
        "approved_by",
        "client_profile_version_id",
        "playbook_version_id",
    ):
        assert stale[key] == artifact_before[key]


@pytest.mark.parametrize("source_kind", ["profile", "playbook"])
def test_failed_staleness_marking_rolls_back_approval(
    source_kind, monkeypatch, client, api, profile_factory, playbook_factory
):
    # Approval and staleness must succeed together: otherwise an old artifact
    # could appear current while retrieval already returns a newer source.
    if source_kind == "profile":
        original = profile_factory(approved=True)
        parent_id = original.client_profile_id
        path, approve = "/client-profiles", api.approve_profile
        target = "src.routers.client_profiles.mark_stale_for_client_profile"
    else:
        original = playbook_factory(approved=True)
        parent_id = original.playbook_id
        path, approve = "/playbooks", api.approve_playbook
        target = "src.routers.playbooks.mark_stale_for_playbook"
    draft = client.put(f"{path}/{parent_id}", json={"changed": True}).json()

    def fail_marking(*args):
        raise RuntimeError("simulated marking failure")

    monkeypatch.setattr(target, fail_marking)
    # Use real request-scoped sessions so dependency cleanup rolls back a failed
    # transaction as it does in production, rather than the shared test session.
    from src.db import get_db
    from src.main import app

    shared_override = app.dependency_overrides.pop(get_db)
    try:
        with pytest.raises(RuntimeError, match="simulated marking failure"):
            approve(parent_id, draft["id"])
        latest = client.get(f"{path}/{parent_id}/latest-approved")
        assert latest.status_code == 200
        assert latest.json()["id"] == str(original.id)
        history = client.get(f"{path}/{parent_id}/versions").json()
        assert history[1]["status"] == "draft"
        assert history[1]["approved_at"] is None
        assert history[1]["approved_by"] is None
    finally:
        app.dependency_overrides[get_db] = shared_override


def test_duplicate_playbook_version_is_rejected_without_losing_original(
    db_session, playbook_factory
):
    original = playbook_factory(approved=True, data={"rule": "Keep me"})
    original_id, approved_at = original.id, original.approved_at
    db_session.add(
        PlaybookVersion(
            id=uuid.uuid4(),
            playbook_id=original.playbook_id,
            version_number=1,
            data={"rule": "Duplicate"},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    saved = db_session.get(PlaybookVersion, original_id)
    assert saved.data == {"rule": "Keep me"}
    assert saved.approved_at == approved_at
