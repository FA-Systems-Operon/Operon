"""AT 4.4 (#72): completed onboarding and review actions leave attributed events."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from tests.test_onboarding_jobs import (
    SourceAwareProvider,
    combined_draft,
    get_job,
    start_draft,
)

from src.audit import AuditAction
from src.models import AuditEvent, Role


@pytest.mark.parametrize("decision", [AuditAction.APPROVE, AuditAction.REJECT])
def test_onboarding_and_review_record_audit_events(
    db_session, demo_client, monkeypatch, sign_in, decision
):
    provider = SourceAwareProvider(combined_draft)
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: provider)
    uploader_http, uploader = sign_in(Role.REVIEWER)
    reviewer_http, reviewer = sign_in(Role.REVIEWER)

    started_at = datetime.now(timezone.utc)
    _, _, started = start_draft(uploader_http, demo_client)
    job = get_job(uploader_http, demo_client, started)
    assert job["status"] == "succeeded", job["error"]

    profile_id = uuid.UUID(job["result_profile_id"])
    draft_id = uuid.UUID(job["result_version_id"])
    url = f"/api/v1/reviews/profiles/{profile_id}/versions/{draft_id}/{decision}"
    if decision == AuditAction.APPROVE:
        result = reviewer_http.post(url)
        assert result.status_code == 201, result.text
        decision_version_id = uuid.UUID(result.json()["version"]["id"])
        assert decision_version_id != draft_id
    else:
        result = reviewer_http.post(
            url, json={"reason": "Client needs to confirm details"}
        )
        assert result.status_code == 200, result.text
        decision_version_id = uuid.UUID(result.json()["id"])
        assert decision_version_id == draft_id
    finished_at = datetime.now(timezone.utc)

    expected_events = (
        (
            AuditAction.JOB_STARTED,
            uploader.id,
            "onboarding_job",
            uuid.UUID(job["id"]),
            None,
        ),
        (
            AuditAction.DRAFT_CREATED,
            uploader.id,
            "client_profile",
            profile_id,
            draft_id,
        ),
        (decision, reviewer.id, "client_profile", profile_id, decision_version_id),
    )
    for action, actor_id, object_type, object_id, version_id in expected_events:
        event = db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == action, AuditEvent.object_id == object_id
            )
        ).one()
        assert event.actor_id == actor_id
        assert event.object_type == object_type
        assert event.version_id == version_id
        assert started_at <= event.created_at <= finished_at
