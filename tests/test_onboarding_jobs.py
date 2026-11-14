"""Task #36: once a client's transcript and intake answers are both uploaded,
one background job runs the onboarding agent on exactly those two files.

Uploading a single file never starts a job, so the agent can't draft from a
partial set. The model is faked so CI needs no Ollama. TestClient runs
background tasks before returning the response, so a started job has finished
by the time the test checks it.
"""

import json
import uuid

import pytest
from sqlalchemy import func, select

from src.ai.provider import ModelResponse, ProviderConfigError, ProviderUnavailable
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

    def generate(self, prompt, *, system=None, json_output=False, output_schema=None):
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
    return {
        "name": "Maya Chen",
        "needs": ["More qualified bookings"],
        "goals": ["30 bookings per month", "Launch a referral program"],
        "source_references": [
            {
                "field": "name",
                "document_id": ids["intake"],
                "quote": "Contact name: Maya Chen",
            },
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
            {
                "field": "goals/1",
                "document_id": ids["intake"],
                "quote": "Goal: Launch a referral program",
            },
        ],
    }


@pytest.fixture
def fake_model(monkeypatch):
    """Install a fake model for the job runner; returns it."""

    def install(build_reply=combined_draft):
        provider = SourceAwareProvider(build_reply)
        monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: provider)
        return provider

    return install


@pytest.fixture
def no_runner(monkeypatch):
    """Start jobs without running them, to see the state right after the start."""
    monkeypatch.setattr(
        "src.routers.onboarding_jobs.run_onboarding_job", lambda *a: None
    )


def upload(client, owner, text, kind, filename=None):
    response = client.post(
        f"/api/v1/clients/{owner.id}/documents",
        files={"file": (filename or f"{kind}.txt", text.encode(), "text/plain")},
        data={"kind": kind},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload_pair(client, owner, transcript=TRANSCRIPT, intake=INTAKE):
    """What the upload page does: the transcript, then the intake answers."""
    return (
        upload(client, owner, transcript, "transcript"),
        upload(client, owner, intake, "intake"),
    )


def start(client, owner, transcript, intake):
    """What the upload page's onUploaded hook does once both files are saved."""
    return client.post(
        f"/api/v1/clients/{owner.id}/onboarding-jobs",
        json={
            "transcript_document_id": transcript["id"],
            "intake_document_id": intake["id"],
        },
    )


def start_draft(client, owner, **texts):
    transcript, intake = upload_pair(client, owner, **texts)
    response = start(client, owner, transcript, intake)
    assert response.status_code == 201, response.text
    return transcript, intake, response.json()


def get_job(client, owner, job):
    response = client.get(f"/api/v1/clients/{owner.id}/onboarding-jobs/{job['id']}")
    assert response.status_code == 200, response.text
    return response.json()


def version_count(db):
    return db.scalar(select(func.count()).select_from(ClientProfileVersion))


def job_count(db):
    return db.scalar(select(func.count()).select_from(OnboardingJob))


# --- Uploads alone never start a draft ---------------------------------------


def test_uploading_files_does_not_start_a_job(client, db_session, demo_client):
    transcript, intake = upload_pair(client, demo_client)

    assert job_count(db_session) == 0
    assert version_count(db_session) == 0
    for document in (transcript, intake):
        assert db_session.get(ExtractedText, uuid.UUID(document["id"])) is None


# --- Starting a draft ---------------------------------------------------------


def test_start_saves_one_pending_job_for_the_pair(client, demo_client, no_runner):
    transcript, intake = upload_pair(client, demo_client)

    response = start(client, demo_client, transcript, intake)

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "pending"
    assert job["client_id"] == str(demo_client.id)
    assert job["transcript_document_id"] == transcript["id"]
    assert job["intake_document_id"] == intake["id"]
    assert job["started_at"] is None and job["result_version_id"] is None
    assert job["result_profile_id"] is None
    assert get_job(client, demo_client, job)["status"] == "pending"


def test_draft_uses_both_files_without_manual_steps(
    client, db_session, demo_client, fake_model
):
    provider = fake_model()

    transcript, intake, job = start_draft(client, demo_client)

    job = get_job(client, demo_client, job)
    assert job["status"] == "succeeded"
    assert job["error"] is None
    assert job["started_at"] and job["finished_at"]
    # Both files were extracted by the job, with no /extract call.
    db_session.expire_all()
    for document in (transcript, intake):
        assert db_session.get(ExtractedText, uuid.UUID(document["id"])) is not None
    assert len(provider.prompts) == 1
    version = db_session.get(ClientProfileVersion, uuid.UUID(job["result_version_id"]))
    # The page links to the draft with both IDs.
    assert job["result_profile_id"] == str(version.client_profile_id)
    assert version.data["name"] == "Maya Chen"
    cited = {ref["document_id"] for ref in version.data["source_references"]}
    assert cited == {transcript["id"], intake["id"]}
    assert version.status.value == "draft"


def test_draft_ignores_the_clients_other_documents(
    client, db_session, demo_client, fake_model
):
    provider = fake_model()
    older = upload(client, demo_client, "Old call: we sell shoes.", "transcript")
    client.post(f"/api/v1/clients/{demo_client.id}/documents/{older['id']}/extract")

    transcript, intake, job = start_draft(client, demo_client)

    sources = json.loads(provider.prompts[0].split("Source documents (JSON):\n")[1])
    assert {s["document_id"] for s in sources} == {transcript["id"], intake["id"]}
    assert get_job(client, demo_client, job)["status"] == "succeeded"


def test_starting_the_same_pair_again_returns_the_same_job(
    client, db_session, demo_client, fake_model
):
    provider = fake_model()
    transcript, intake, job = start_draft(client, demo_client)

    again = start(client, demo_client, transcript, intake)

    assert again.status_code == 200
    assert again.json()["id"] == job["id"]
    assert len(provider.prompts) == 1
    assert job_count(db_session) == 1
    assert version_count(db_session) == 1


def test_starting_a_failed_pair_again_queues_it_once_more(
    client, db_session, demo_client, monkeypatch
):
    def not_configured():
        raise ProviderConfigError("OLLAMA_MODEL is not set.")

    monkeypatch.setattr("src.onboarding_jobs.get_provider", not_configured)
    transcript, intake, job = start_draft(client, demo_client)
    assert get_job(client, demo_client, job)["status"] == "failed"

    provider = SourceAwareProvider(combined_draft)
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: provider)
    again = start(client, demo_client, transcript, intake)

    assert again.status_code == 200
    assert again.json()["id"] == job["id"]
    finished = get_job(client, demo_client, job)
    assert finished["status"] == "succeeded"
    assert finished["error"] is None
    assert job_count(db_session) == 1


def test_a_new_pair_gets_its_own_job(client, db_session, demo_client, fake_model):
    fake_model()
    _, _, first = start_draft(client, demo_client)
    _, _, second = start_draft(client, demo_client)

    assert first["id"] != second["id"]
    assert get_job(client, demo_client, second)["status"] == "succeeded"
    assert job_count(db_session) == 2


def test_concurrent_start_for_the_same_pair_returns_the_winner(
    client, db_session, demo_client, no_runner, monkeypatch
):
    transcript, intake = upload_pair(client, demo_client)
    winner = start(client, demo_client, transcript, intake).json()
    # This request checked for a job just before the other one saved its own.
    real_lookup = __import__(
        "src.routers.onboarding_jobs", fromlist=["_job_for_pair"]
    )._job_for_pair
    calls = {"count": 0}

    def late_lookup(db, body):
        calls["count"] += 1
        return None if calls["count"] == 1 else real_lookup(db, body)

    monkeypatch.setattr("src.routers.onboarding_jobs._job_for_pair", late_lookup)

    response = start(client, demo_client, transcript, intake)

    assert response.status_code == 200
    assert response.json()["id"] == winner["id"]
    assert job_count(db_session) == 1


def test_existing_client_profile_gets_the_new_draft(
    client, db_session, demo_client, fake_model, profile_factory
):
    fake_model()
    existing = profile_factory()

    _, _, job = start_draft(client, demo_client)

    job = get_job(client, demo_client, job)
    version = db_session.get(ClientProfileVersion, uuid.UUID(job["result_version_id"]))
    assert version.client_profile_id == existing.client_profile_id
    assert version.version_number == 2
    assert db_session.scalar(select(func.count()).select_from(ClientProfile)) == 1


# --- Checks on the two documents ---------------------------------------------


def test_start_requires_a_transcript_and_an_intake(client, demo_client, no_runner):
    transcript, intake = upload_pair(client, demo_client)

    swapped = start(client, demo_client, intake, transcript)
    two_transcripts = start(client, demo_client, transcript, transcript)

    assert swapped.status_code == 422
    assert swapped.json()["detail"] == (
        "transcript_document_id must be a transcript document"
    )
    assert two_transcripts.status_code == 422
    assert two_transcripts.json()["detail"] == (
        "intake_document_id must be a intake document"
    )


def test_start_rejects_documents_without_a_kind(client, demo_client, no_runner):
    response = client.post(
        f"/api/v1/clients/{demo_client.id}/documents",
        files={"file": ("call.txt", TRANSCRIPT.encode(), "text/plain")},
    )
    untyped = response.json()
    _, intake = upload_pair(client, demo_client)

    assert start(client, demo_client, untyped, intake).status_code == 422


def test_start_rejects_missing_or_other_clients_documents(
    client, db_session, demo_client, client_factory, no_runner
):
    transcript, intake = upload_pair(client, demo_client)
    other = client_factory("Other Client")
    unknown = {"id": str(uuid.uuid4())}

    missing_intake = start(client, demo_client, transcript, unknown)
    from_other_client = start(client, other, transcript, intake)

    assert missing_intake.status_code == 404
    assert missing_intake.json()["detail"] == "Intake not found"
    assert from_other_client.status_code == 404
    assert from_other_client.json()["detail"] == "Transcript not found"
    assert job_count(db_session) == 0


def test_start_for_unknown_client_returns_404(client, demo_client):
    transcript, intake = upload_pair(client, demo_client)
    nobody = type("Owner", (), {"id": uuid.uuid4()})

    response = start(client, nobody, transcript, intake)

    assert response.status_code == 404
    assert response.json()["detail"] == "Client not found"


def test_start_with_invalid_ids_returns_422(client, demo_client):
    response = client.post(
        f"/api/v1/clients/{demo_client.id}/onboarding-jobs",
        json={"transcript_document_id": "not-a-uuid"},
    )

    assert response.status_code == 422


# --- Failures -----------------------------------------------------------------


def test_provider_failure_marks_the_job_failed_and_saves_nothing(
    client, db_session, demo_client, monkeypatch
):
    def unavailable():
        raise ProviderUnavailable("connection refused")

    monkeypatch.setattr("src.onboarding_jobs.get_provider", unavailable)
    # With no retries left the job fails at once; retries are covered in
    # test_onboarding_job_recovery.py (#37).
    monkeypatch.setattr(settings, "JOB_RETRY_ATTEMPTS", 0)

    transcript, _, job = start_draft(client, demo_client)

    job = get_job(client, demo_client, job)
    assert job["status"] == "failed"
    assert job["error"] == "AI provider failed: ProviderUnavailable"
    assert job["finished_at"] is not None
    assert version_count(db_session) == 0
    # The uploads are kept, and so is their extracted text.
    assert db_session.get(ExtractedText, uuid.UUID(transcript["id"])) is not None


def test_unsupported_evidence_marks_the_job_failed_and_saves_nothing(
    client, db_session, demo_client, fake_model
):
    def invented_quote(ids):
        draft = combined_draft(ids)
        draft["source_references"][1]["quote"] = "Words nobody said"
        return draft

    fake_model(invented_quote)

    _, _, job = start_draft(client, demo_client)

    job = get_job(client, demo_client, job)
    assert job["status"] == "failed"
    assert "exactly in its source document" in job["error"]
    assert version_count(db_session) == 0


def test_malformed_model_reply_marks_the_job_failed(
    client, db_session, demo_client, fake_model
):
    fake_model(lambda ids: {"name": 42})

    _, _, job = start_draft(client, demo_client)

    job = get_job(client, demo_client, job)
    assert job["status"] == "failed"
    assert job["error"] == "Agent reply did not match the client profile format"


def test_missing_stored_file_marks_the_job_failed(
    db_session, storage, demo_client, fake_model, make_pair
):
    provider = fake_model()
    job = make_pair()
    intake_key = f"{demo_client.id}/{job.intake_document_id}"
    storage.delete(intake_key)

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
    db_session, storage, fake_model, make_pair, status
):
    provider = fake_model()
    job = make_pair(status=status)

    run_onboarding_job(job.id, storage)

    db_session.expire_all()
    assert db_session.get(OnboardingJob, job.id).status == status
    assert provider.prompts == []
    assert version_count(db_session) == 0


def test_unknown_job_id_is_ignored(storage, database):
    run_onboarding_job(uuid.uuid4(), storage)  # must not raise


# --- Status endpoint ----------------------------------------------------------


def test_job_status_is_scoped_to_the_client(
    client, demo_client, client_factory, no_runner
):
    _, _, job = start_draft(client, demo_client)
    other = client_factory("Other Client")

    response = client.get(f"/api/v1/clients/{other.id}/onboarding-jobs/{job['id']}")

    assert response.status_code == 404


def test_job_status_404_for_unknown_job(client, demo_client):
    response = client.get(
        f"/api/v1/clients/{demo_client.id}/onboarding-jobs/{uuid.uuid4()}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Onboarding job not found"
