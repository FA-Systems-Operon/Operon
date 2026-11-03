"""AT 3.1 (#47): Given a staff member on the upload screen, when they upload a
transcript and intake answers for a client, then a job is saved as "pending" and
a draft profile is generated without any manual steps.

Each test sends exactly the requests the upload page sends: the transcript, then
the intake answers, then "start the draft" with both document IDs. Nothing else
is called; the job extracts the text, runs the agent and saves the draft itself.
It also checks the job survives a restart and that model errors are handled.

The model is faked so CI needs no Ollama. The page side (it sends those three
requests) is frontend/src/AddSources.acceptance.test.tsx.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from tests.test_onboarding_job_recovery import FlakyProvider
from tests.test_onboarding_jobs import get_job, start, upload_pair

from src.ai.provider import ProviderConfigError, ProviderUnavailable
from src.config import settings
from src.db import SessionLocal
from src.main import app
from src.models import ClientProfile, JobStatus, OnboardingJob
from src.onboarding_jobs import _execute, run_next_job, run_onboarding_job


@pytest.fixture
def model(monkeypatch):
    """Install a fake model for the job runner; returns it. It can fail its first
    `failures` calls with `error`, like Ollama being down."""

    def install(failures=0, error=ProviderUnavailable):
        fake = FlakyProvider(failures, error)
        monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: fake)
        return fake

    return install


@pytest.fixture
def status_when_run_starts(monkeypatch):
    """Records each job's status at the moment its run starts. It reads through a
    new database session, which only sees what was committed."""
    seen = {}

    def run_and_record(job_id, storage):
        with SessionLocal() as db:
            seen[str(job_id)] = db.get(OnboardingJob, job_id).status.value
        run_onboarding_job(job_id, storage)

    monkeypatch.setattr(
        "src.routers.onboarding_jobs.run_onboarding_job", run_and_record
    )
    return seen


def upload_and_start(client, owner):
    """What the staff member does on the upload page: both files, then the start."""
    transcript, intake = upload_pair(client, owner)
    response = start(client, owner, transcript, intake)
    assert response.status_code == 201, response.text
    return transcript, intake, response.json()


def drafts_of(client, db, owner):
    """The client's profile versions, read through the API like a reviewer would."""
    profile = db.scalar(
        select(ClientProfile).where(ClientProfile.client_id == owner.id)
    )
    if profile is None:
        return []
    response = client.get(f"/client-profiles/{profile.id}/versions")
    assert response.status_code == 200, response.text
    return response.json()


def assert_draft_from(job, drafts, transcript, intake):
    """The job's result is the client's one draft, built from both uploaded files."""
    assert job["status"] == "succeeded"
    assert job["error"] is None
    [draft] = drafts
    assert draft["id"] == job["result_version_id"]
    assert draft["status"] == "draft"
    assert draft["data"]["name"] == "Maya Chen"
    assert draft["data"]["needs"] and draft["data"]["goals"]
    cited = {ref["document_id"] for ref in draft["data"]["source_references"]}
    assert cited == {transcript["id"], intake["id"]}


def test_upload_saves_a_pending_job_and_drafts_without_manual_steps(
    client, db_session, demo_client, model, status_when_run_starts
):
    provider = model()

    transcript, intake, started = upload_and_start(client, demo_client)

    # The job was saved as pending, and was still pending when its run began.
    assert started["status"] == "pending"
    assert status_when_run_starts == {started["id"]: "pending"}
    # With no further requests, the agent ran once and the draft was saved.
    job = get_job(client, demo_client, started)
    assert len(provider.prompts) == 1
    drafts = drafts_of(client, db_session, demo_client)
    assert_draft_from(job, drafts, transcript, intake)


@pytest.mark.parametrize("stopped", ["before_the_run", "during_the_run"])
def test_job_left_by_a_restart_is_drafted_when_the_api_starts_again(
    client, db_session, demo_client, model, monkeypatch, tmp_path, stopped
):
    model()
    # The API stops right after saving the job, so the start call's run never happens.
    monkeypatch.setattr(
        "src.routers.onboarding_jobs.run_onboarding_job", lambda *args: None
    )
    transcript, intake, started = upload_and_start(client, demo_client)
    if stopped == "during_the_run":
        # What a crash mid-run leaves: running, with a claim that has run out.
        db_session.execute(
            update(OnboardingJob)
            .where(OnboardingJob.id == uuid.UUID(started["id"]))
            .values(
                status=JobStatus.RUNNING,
                attempts=1,
                lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        )
        db_session.commit()
    assert drafts_of(client, db_session, demo_client) == []

    # Signals when a run has finished and saved its result.
    finished = threading.Event()

    def execute_and_signal(*args):
        _execute(*args)
        finished.set()

    monkeypatch.setattr("src.onboarding_jobs._execute", execute_and_signal)

    # Start the API again. Its background worker finds the job on its own.
    monkeypatch.setattr(settings, "BACKGROUND_WORKER_ENABLED", True)
    monkeypatch.setattr(settings, "JOB_POLL_SECONDS", 0.05)
    # Where the uploaded files were saved in this test.
    monkeypatch.setattr(settings, "STORAGE_DIR", str(tmp_path))
    with TestClient(app):
        assert finished.wait(timeout=10), "the worker did not run the job"

    db_session.expire_all()
    job = get_job(client, demo_client, started)
    drafts = drafts_of(client, db_session, demo_client)
    assert_draft_from(job, drafts, transcript, intake)


def test_model_outage_keeps_the_job_and_drafts_once_the_model_is_back(
    client, db_session, demo_client, model, monkeypatch, storage
):
    model(failures=1, error=ProviderUnavailable)
    monkeypatch.setattr(settings, "JOB_RETRY_DELAY_SECONDS", 0)

    transcript, intake, started = upload_and_start(client, demo_client)

    # The first try failed: the job waits for a retry, with a reason, and no draft.
    job = get_job(client, demo_client, started)
    assert job["status"] == "pending"
    assert job["attempts"] == 1
    assert job["error"] == "AI provider failed: ProviderUnavailable"
    assert drafts_of(client, db_session, demo_client) == []

    # The model is back; the worker's next round retries the job.
    assert run_next_job(storage) is True

    job = get_job(client, demo_client, started)
    drafts = drafts_of(client, db_session, demo_client)
    assert_draft_from(job, drafts, transcript, intake)


def test_unconfigured_model_fails_with_a_reason_and_can_be_started_again(
    client, db_session, demo_client, model
):
    model(failures=1, error=ProviderConfigError)

    transcript, intake, started = upload_and_start(client, demo_client)

    # A setup problem is not retried: the job fails at once and says why.
    job = get_job(client, demo_client, started)
    assert job["status"] == "failed"
    assert job["error"].startswith("AI provider is not configured")
    assert drafts_of(client, db_session, demo_client) == []

    # Once it's set up, asking for a draft from the same two files restarts that job.
    again = start(client, demo_client, transcript, intake)
    assert again.status_code == 200
    assert again.json()["id"] == started["id"]

    job = get_job(client, demo_client, started)
    drafts = drafts_of(client, db_session, demo_client)
    assert_draft_from(job, drafts, transcript, intake)
