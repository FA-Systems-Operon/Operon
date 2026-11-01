"""Task #36: an upload starts a background job that runs the onboarding agent.

The model is faked so CI needs no Ollama. TestClient runs background tasks
before returning the response, so each upload's job has finished by the time
the test checks it.
"""

import json
import uuid

import pytest
from sqlalchemy import func, select

from src.ai.provider import ModelResponse, ProviderUnavailable
from src.config import settings
from src.models import (
    ClientProfile,
    ClientProfileVersion,
    ExtractedText,
    JobStatus,
    OnboardingJob,
)
from src.onboarding_jobs import run_onboarding_job

TRANSCRIPT = (
    "Discovery call\n\n"
    "Maya Chen: I need more qualified bookings.\n"
    "Maya Chen: We want 30 bookings per month.\n"
)
INTAKE = (
    "Client intake form\nContact name: Maya Chen\nGoal: Launch a referral program\n"
)


class SourceAwareProvider:
    """Fake model that cites whatever document IDs the prompt supplied."""

    def __init__(self, build_reply):
        self.build_reply = build_reply
        self.prompts = []

    def generate(self, prompt, *, system=None, json_output=False):
        self.prompts.append(prompt)
        sources = json.loads(prompt.split("Source documents (JSON):\n", 1)[1])
        ids = {source["kind"]: source["document_id"] for source in sources}
        return ModelResponse(
            text=json.dumps(self.build_reply(ids)),
            provider="fake",
            model="fake-model",
            duration_ms=1,
        )


def combined_draft(ids):
    """A valid draft backed by both the transcript and the intake form."""
    references = [
        {
            "field": "needs/0",
            "document_id": ids["transcript"],
            "quote": "I need more qualified bookings.",
        },
        {
            "field": "goals/0",
            "document_id": ids["transcript"],
            "quote": "We want 30 bookings per month.",
        },
    ]
    draft = {
        "name": None,
        "needs": ["More qualified bookings"],
        "goals": ["30 bookings per month"],
        "source_references": references,
    }
    if "intake" in ids:
        draft["name"] = "Maya Chen"
        draft["goals"].append("Launch a referral program")
        references += [
            {
                "field": "name",
                "document_id": ids["intake"],
                "quote": "Contact name: Maya Chen",
            },
            {
                "field": "goals/1",
                "document_id": ids["intake"],
                "quote": "Goal: Launch a referral program",
            },
        ]
    return draft


@pytest.fixture
def fake_model(monkeypatch):
    """Install a fake model for the job runner; returns a setter for its reply."""

    def install(build_reply=combined_draft):
        provider = SourceAwareProvider(build_reply)
        monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: provider)
        return provider

    return install


def upload(client, owner, text, kind, filename=None):
    response = client.post(
        f"/api/v1/clients/{owner.id}/documents",
        files={"file": (filename or f"{kind}.txt", text.encode(), "text/plain")},
        data={"kind": kind},
    )
    assert response.status_code == 201, response.text
    return response.json()


def job_for(client, owner, document):
    response = client.get(
        f"/api/v1/clients/{owner.id}/documents/{document['id']}/onboarding-job"
    )
    assert response.status_code == 200, response.text
    return response.json()


def version_count(db):
    return db.scalar(select(func.count()).select_from(ClientProfileVersion))


def test_upload_saves_a_pending_job_with_the_document(client, demo_client, monkeypatch):
    # Stop the runner so the state right after the upload commit is visible.
    monkeypatch.setattr("src.routers.documents.run_onboarding_job", lambda *a: None)

    document = upload(client, demo_client, TRANSCRIPT, "transcript")

    job = job_for(client, demo_client, document)
    assert job["status"] == "pending"
    assert job["document_id"] == document["id"]
    assert job["client_id"] == str(demo_client.id)
    assert job["started_at"] is None and job["result_version_id"] is None


def test_transcript_and_intake_uploads_produce_a_draft_without_manual_steps(
    client, db_session, demo_client, fake_model
):
    provider = fake_model()

    transcript = upload(client, demo_client, TRANSCRIPT, "transcript")
    first = job_for(client, demo_client, transcript)
    intake = upload(client, demo_client, INTAKE, "intake")
    second = job_for(client, demo_client, intake)

    assert first["status"] == second["status"] == "succeeded"
    assert first["error"] is None and second["error"] is None
    assert second["started_at"] and second["finished_at"]
    # Both uploads were extracted automatically, with no /extract call.
    db_session.expire_all()
    for document in (transcript, intake):
        assert db_session.get(ExtractedText, uuid.UUID(document["id"])) is not None
    # The second run saw both documents and drew on both.
    assert transcript["id"] in provider.prompts[1]
    assert intake["id"] in provider.prompts[1]

    version = db_session.get(
        ClientProfileVersion, uuid.UUID(second["result_version_id"])
    )
    assert version.data["name"] == "Maya Chen"
    assert version.status.value == "draft"
    # Both runs added versions to the same profile instead of making new ones.
    assert version.version_number == 2
    assert db_session.scalar(select(func.count()).select_from(ClientProfile)) == 1


def test_existing_client_profile_gets_the_new_draft(
    client, db_session, demo_client, fake_model, profile_factory
):
    fake_model()
    existing = profile_factory()

    document = upload(client, demo_client, TRANSCRIPT, "transcript")

    job = job_for(client, demo_client, document)
    version = db_session.get(ClientProfileVersion, uuid.UUID(job["result_version_id"]))
    assert version.client_profile_id == existing.client_profile_id
    assert version.version_number == 2


def test_provider_failure_marks_the_job_failed_and_saves_nothing(
    client, db_session, demo_client, monkeypatch
):
    def unavailable():
        raise ProviderUnavailable("connection refused")

    monkeypatch.setattr("src.onboarding_jobs.get_provider", unavailable)
    # With no retries left the job fails at once; retries are covered in
    # test_onboarding_job_recovery.py (#37).
    monkeypatch.setattr(settings, "JOB_RETRY_ATTEMPTS", 0)

    document = upload(client, demo_client, TRANSCRIPT, "transcript")

    job = job_for(client, demo_client, document)
    assert job["status"] == "failed"
    assert job["error"] == "AI provider failed: ProviderUnavailable"
    assert job["finished_at"] is not None
    assert version_count(db_session) == 0
    # The upload itself is kept, and so is its extracted text.
    assert db_session.get(ExtractedText, uuid.UUID(document["id"])) is not None


def test_unsupported_evidence_marks_the_job_failed_and_saves_nothing(
    client, db_session, demo_client, fake_model
):
    def invented_quote(ids):
        draft = combined_draft(ids)
        draft["source_references"][0]["quote"] = "Words nobody said"
        return draft

    fake_model(invented_quote)

    document = upload(client, demo_client, TRANSCRIPT, "transcript")

    job = job_for(client, demo_client, document)
    assert job["status"] == "failed"
    assert "exactly in its source document" in job["error"]
    assert version_count(db_session) == 0


def test_malformed_model_reply_marks_the_job_failed(
    client, db_session, demo_client, fake_model
):
    fake_model(lambda ids: {"name": 42})

    document = upload(client, demo_client, TRANSCRIPT, "transcript")

    job = job_for(client, demo_client, document)
    assert job["status"] == "failed"
    assert job["error"] == "Agent reply did not match the client profile format"


def test_missing_stored_file_marks_the_job_failed(
    db_session, storage, stored_document, demo_client, fake_model
):
    provider = fake_model()
    document = stored_document(data=TRANSCRIPT.encode())
    job = OnboardingJob(client_id=demo_client.id, document_id=document.id)
    db_session.add(job)
    db_session.commit()
    storage.delete(document.storage_key)

    run_onboarding_job(job.id, storage)

    db_session.expire_all()
    job = db_session.get(OnboardingJob, job.id)
    assert job.status == JobStatus.FAILED
    assert job.error == "Stored document file is unavailable"
    assert provider.prompts == []


@pytest.mark.parametrize(
    "status", [JobStatus.RUNNING, JobStatus.SUCCEEDED, JobStatus.FAILED]
)
def test_a_job_that_is_not_pending_is_not_run_again(
    db_session, storage, stored_document, demo_client, fake_model, status
):
    provider = fake_model()
    document = stored_document(data=TRANSCRIPT.encode())
    job = OnboardingJob(
        client_id=demo_client.id, document_id=document.id, status=status
    )
    db_session.add(job)
    db_session.commit()

    run_onboarding_job(job.id, storage)

    db_session.expire_all()
    assert db_session.get(OnboardingJob, job.id).status == status
    assert provider.prompts == []
    assert version_count(db_session) == 0


def test_unknown_job_id_is_ignored(storage, database):
    run_onboarding_job(uuid.uuid4(), storage)  # must not raise


def test_job_status_is_scoped_to_the_client(
    client, demo_client, client_factory, monkeypatch
):
    monkeypatch.setattr("src.routers.documents.run_onboarding_job", lambda *a: None)
    document = upload(client, demo_client, TRANSCRIPT, "transcript")
    other = client_factory("Other Client")

    response = client.get(
        f"/api/v1/clients/{other.id}/documents/{document['id']}/onboarding-job"
    )

    assert response.status_code == 404


def test_job_status_404_for_unknown_document(client, demo_client):
    response = client.get(
        f"/api/v1/clients/{demo_client.id}/documents/{uuid.uuid4()}/onboarding-job"
    )

    assert response.status_code == 404
