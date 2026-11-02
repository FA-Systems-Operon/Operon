"""Task #37: jobs are saved as pending before they run, survive a crash, and
are retried. The model is faked, so no Ollama is needed.

A "crash" is simulated by leaving a job in the state a dead runner would leave
it: pending and never started, or running with a lease that has run out.
"""

import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update
from tests.test_onboarding_jobs import (
    SourceAwareProvider,
    combined_draft,
    start_draft,
)

from src.ai.provider import ProviderTimeout, ProviderUnavailable
from src.config import settings
from src.db import SessionLocal
from src.models import ClientProfileVersion, JobStatus, OnboardingJob
from src.onboarding_jobs import (
    _record_failure,
    recover_abandoned_jobs,
    run_next_job,
    run_onboarding_job,
    start_worker,
)


class FlakyProvider(SourceAwareProvider):
    """Fails the first `failures` calls, then answers like the normal fake."""

    def __init__(self, failures, error=ProviderUnavailable):
        super().__init__(combined_draft)
        self.failures = failures
        self.error = error
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error("model is down")
        return super().generate(prompt, **kwargs)


@pytest.fixture
def provider(monkeypatch):
    def install(failures=0, error=ProviderUnavailable):
        fake = FlakyProvider(failures, error)
        monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: fake)
        return fake

    return install


@pytest.fixture
def no_runner_on_start(monkeypatch):
    """Starting a draft saves its pending job but nothing runs it, as after a crash."""
    monkeypatch.setattr(
        "src.routers.onboarding_jobs.run_onboarding_job", lambda *a: None
    )


@pytest.fixture
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(settings, "JOB_RETRY_DELAY_SECONDS", 0)


def now():
    return datetime.now(timezone.utc)


def job_of(db, job):
    db.expire_all()
    return db.get(OnboardingJob, uuid.UUID(job["id"]))


def version_count(db):
    return db.scalar(select(func.count()).select_from(ClientProfileVersion))


def set_job(db, job, **values):
    db.execute(update(OnboardingJob).where(OnboardingJob.id == job.id).values(**values))
    db.commit()


# --- Persist before execute ---------------------------------------------------


def test_job_saved_before_a_crash_is_run_later(
    client, db_session, demo_client, provider, no_runner_on_start, storage
):
    provider()
    _, _, started = start_draft(client, demo_client)
    job = job_of(db_session, started)
    assert job.status == JobStatus.PENDING and job.attempts == 0

    # The API "restarts": the start call's task never ran; the worker finds the job.
    assert run_next_job(storage) is True

    job = job_of(db_session, started)
    assert job.status == JobStatus.SUCCEEDED
    assert job.attempts == 1
    assert version_count(db_session) == 1
    assert run_next_job(storage) is False


# --- Retries ------------------------------------------------------------------


def test_temporary_failure_is_retried_later(
    client, db_session, demo_client, provider, monkeypatch, storage
):
    monkeypatch.setattr(settings, "JOB_RETRY_DELAY_SECONDS", 30)
    provider(failures=1)
    before = now()

    _, _, started = start_draft(client, demo_client)

    job = job_of(db_session, started)
    assert job.status == JobStatus.PENDING
    assert job.attempts == 1
    assert job.error == "AI provider failed: ProviderUnavailable"
    assert job.next_attempt_at >= before + timedelta(seconds=30)
    assert job.lease_expires_at is None
    assert version_count(db_session) == 0
    # Not due yet, so nothing runs.
    assert run_next_job(storage) is False

    response = client.get(
        f"/api/v1/clients/{demo_client.id}/onboarding-jobs/{started['id']}"
    )
    assert response.json()["attempts"] == 1
    assert response.json()["next_attempt_at"] is not None


def test_retry_succeeds_once_due(
    client, db_session, demo_client, provider, no_retry_delay, storage
):
    fake = provider(failures=1, error=ProviderTimeout)
    _, _, started = start_draft(client, demo_client)

    assert run_next_job(storage) is True

    job = job_of(db_session, started)
    assert job.status == JobStatus.SUCCEEDED
    assert job.attempts == 2
    assert job.error is None
    assert fake.calls == 2
    assert version_count(db_session) == 1


def test_job_fails_when_retries_are_used_up(
    client, db_session, demo_client, provider, no_retry_delay, monkeypatch, storage
):
    monkeypatch.setattr(settings, "JOB_RETRY_ATTEMPTS", 2)
    fake = provider(failures=99)
    _, _, started = start_draft(client, demo_client)

    while run_next_job(storage):
        pass

    job = job_of(db_session, started)
    assert job.status == JobStatus.FAILED
    assert job.attempts == 3  # first try + 2 retries
    assert fake.calls == 3
    assert job.finished_at is not None
    assert version_count(db_session) == 0


def test_bad_model_output_is_not_retried(
    client, db_session, demo_client, monkeypatch, storage
):
    fake = SourceAwareProvider(lambda ids: {"name": 42})
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: fake)

    _, _, started = start_draft(client, demo_client)

    job = job_of(db_session, started)
    assert job.status == JobStatus.FAILED
    assert job.attempts == 1
    assert run_next_job(storage) is False


# --- Crash while running ------------------------------------------------------


def test_job_abandoned_mid_run_is_requeued_and_finished(
    client, db_session, demo_client, provider, no_runner_on_start, storage
):
    provider()
    _, _, started = start_draft(client, demo_client)
    job = job_of(db_session, started)
    # The runner claimed it and then the process died.
    set_job(
        db_session,
        job,
        status=JobStatus.RUNNING,
        attempts=1,
        started_at=now() - timedelta(minutes=20),
        lease_expires_at=now() - timedelta(minutes=10),
    )

    assert recover_abandoned_jobs() == 1

    job = job_of(db_session, started)
    assert job.status == JobStatus.PENDING
    assert job.error == "Previous attempt stopped before finishing"
    assert run_next_job(storage) is True
    job = job_of(db_session, started)
    assert job.status == JobStatus.SUCCEEDED
    assert job.attempts == 2
    assert version_count(db_session) == 1


def test_abandoned_job_without_attempts_left_is_failed(
    client, db_session, demo_client, no_runner_on_start, monkeypatch
):
    monkeypatch.setattr(settings, "JOB_RETRY_ATTEMPTS", 1)
    _, _, started = start_draft(client, demo_client)
    set_job(
        db_session,
        job_of(db_session, started),
        status=JobStatus.RUNNING,
        attempts=2,
        lease_expires_at=now() - timedelta(seconds=1),
    )

    assert recover_abandoned_jobs() == 1

    job = job_of(db_session, started)
    assert job.status == JobStatus.FAILED
    assert "no attempts left" in job.error
    assert job.finished_at is not None


def test_running_job_with_a_live_lease_is_left_alone(
    client, db_session, demo_client, no_runner_on_start, storage
):
    _, _, started = start_draft(client, demo_client)
    set_job(
        db_session,
        job_of(db_session, started),
        status=JobStatus.RUNNING,
        attempts=1,
        lease_expires_at=now() + timedelta(minutes=5),
    )

    assert recover_abandoned_jobs() == 0
    assert job_of(db_session, started).status == JobStatus.RUNNING
    assert run_next_job(storage) is False


def test_run_that_lost_its_claim_does_not_save_a_second_draft(
    client, db_session, demo_client, no_runner_on_start, monkeypatch, storage
):
    """A slow run whose lease ran out and was claimed again must not save."""
    _, _, started = start_draft(client, demo_client)
    job = job_of(db_session, started)

    def slow_reply(ids):
        # While the model "thinks", recovery hands the job to a new attempt.
        with SessionLocal() as other:
            other.execute(
                update(OnboardingJob)
                .where(OnboardingJob.id == job.id)
                .values(attempts=OnboardingJob.attempts + 1)
            )
            other.commit()
        return combined_draft(ids)

    fake = SourceAwareProvider(slow_reply)
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: fake)

    run_onboarding_job(job.id, storage)

    job = job_of(db_session, started)
    assert job.status == JobStatus.RUNNING  # still owned by the newer attempt
    assert job.attempts == 2
    assert job.result_version_id is None
    assert version_count(db_session) == 0


# --- Claiming -----------------------------------------------------------------


def test_job_locked_by_another_runner_is_skipped(
    client, db_session, demo_client, provider, no_runner_on_start, storage
):
    provider()
    _, _, started = start_draft(client, demo_client)
    job = job_of(db_session, started)

    with SessionLocal() as other:
        # Another runner is in the middle of claiming this row.
        other.execute(
            select(OnboardingJob).where(OnboardingJob.id == job.id).with_for_update()
        )
        assert run_next_job(storage) is False
        other.rollback()

    assert run_next_job(storage) is True


def test_start_task_and_worker_never_both_run_a_job(
    client, db_session, demo_client, provider, no_runner_on_start, storage
):
    fake = provider()
    _, _, started = start_draft(client, demo_client)
    job = job_of(db_session, started)

    assert run_next_job(storage) is True
    run_onboarding_job(job.id, storage)  # the start call's task arrives late

    assert fake.calls == 1
    assert job_of(db_session, started).attempts == 1


# --- Worker thread ------------------------------------------------------------


def test_worker_thread_recovers_and_runs_pending_jobs(
    client, db_session, demo_client, provider, no_runner_on_start, monkeypatch, storage
):
    provider()
    monkeypatch.setattr(settings, "JOB_POLL_SECONDS", 0.05)
    _, _, fresh = start_draft(client, demo_client)
    _, _, crashed = start_draft(client, demo_client)
    set_job(
        db_session,
        job_of(db_session, crashed),
        status=JobStatus.RUNNING,
        attempts=1,
        lease_expires_at=now() - timedelta(seconds=1),
    )

    stop = start_worker(storage_factory=lambda: storage)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            statuses = {job_of(db_session, d).status for d in (fresh, crashed)}
            if statuses == {JobStatus.SUCCEEDED}:
                break
            time.sleep(0.05)
    finally:
        stop()

    assert job_of(db_session, fresh).status == JobStatus.SUCCEEDED
    assert job_of(db_session, crashed).status == JobStatus.SUCCEEDED
    assert not any(t.name == "onboarding-worker" for t in threading.enumerate())


@pytest.mark.parametrize("enabled", [True, False])
def test_app_startup_starts_the_worker_only_when_enabled(
    database, monkeypatch, enabled
):
    from fastapi.testclient import TestClient

    from src.main import app

    monkeypatch.setattr(settings, "BACKGROUND_WORKER_ENABLED", enabled)
    monkeypatch.setattr(settings, "JOB_POLL_SECONDS", 0.05)

    with TestClient(app):
        running = any(t.name == "onboarding-worker" for t in threading.enumerate())

    assert running is enabled
    assert not any(t.name == "onboarding-worker" for t in threading.enumerate())


def test_worker_keeps_going_after_a_failed_round(
    client,
    db_session,
    demo_client,
    provider,
    no_runner_on_start,
    monkeypatch,
    storage,
    caplog,
):
    provider()
    monkeypatch.setattr(settings, "JOB_POLL_SECONDS", 0.05)
    _, _, started = start_draft(client, demo_client)
    rounds = {"count": 0}
    real_recover = recover_abandoned_jobs

    def flaky_recover():
        rounds["count"] += 1
        if rounds["count"] == 1:
            raise RuntimeError("database briefly unreachable")
        return real_recover()

    monkeypatch.setattr("src.onboarding_jobs.recover_abandoned_jobs", flaky_recover)

    stop = start_worker(storage_factory=lambda: storage)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if job_of(db_session, started).status == JobStatus.SUCCEEDED:
                break
            time.sleep(0.05)
    finally:
        stop()

    assert job_of(db_session, started).status == JobStatus.SUCCEEDED
    assert "Onboarding worker round failed" in caplog.text


def test_failure_from_a_run_that_lost_its_claim_changes_nothing(
    client, db_session, demo_client, no_runner_on_start, caplog
):
    _, _, started = start_draft(client, demo_client)
    job = job_of(db_session, started)
    set_job(db_session, job, status=JobStatus.RUNNING, attempts=2)

    with SessionLocal() as db:
        # Attempt 1 reports its failure after attempt 2 took over.
        _record_failure(db, job.id, 1, ProviderUnavailable("refused"))

    job = job_of(db_session, started)
    assert job.status == JobStatus.RUNNING
    assert job.attempts == 2
    assert job.error is None
    assert "lost its claim before failing" in caplog.text


def test_job_taken_between_selecting_and_claiming_is_not_run(
    client,
    db_session,
    demo_client,
    provider,
    no_runner_on_start,
    monkeypatch,
    storage,
):
    fake = provider()
    start_draft(client, demo_client)
    monkeypatch.setattr("src.onboarding_jobs._claim", lambda db, job_id: None)

    assert run_next_job(storage) is True
    assert fake.calls == 0


def test_starting_a_failed_pair_again_resets_its_attempts(
    client, db_session, demo_client, provider, no_retry_delay, monkeypatch, storage
):
    monkeypatch.setattr(settings, "JOB_RETRY_ATTEMPTS", 1)
    fake = provider(failures=2)
    transcript, intake, started = start_draft(client, demo_client)
    while run_next_job(storage):
        pass
    assert job_of(db_session, started).status == JobStatus.FAILED
    assert job_of(db_session, started).attempts == 2

    again = client.post(
        f"/api/v1/clients/{demo_client.id}/onboarding-jobs",
        json={
            "transcript_document_id": transcript["id"],
            "intake_document_id": intake["id"],
        },
    )

    assert again.status_code == 200
    job = job_of(db_session, started)
    assert job.status == JobStatus.SUCCEEDED
    assert job.attempts == 1
    assert job.error is None
    assert fake.calls == 3
