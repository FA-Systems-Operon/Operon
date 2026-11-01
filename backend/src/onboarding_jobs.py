"""Run the onboarding agent on a client's documents after an upload (#36, #37).

The upload endpoint commits a pending OnboardingJob together with the document,
before anything runs, so a crash can't lose it. Two things then run jobs:

- a FastAPI background task started by the upload, so new jobs start at once;
- a single worker thread (start_worker) that picks up pending jobs, including
  ones left behind by a crash or restart, and retries temporary failures.

Status moves pending -> running -> succeeded | failed, and back to pending when
a temporary failure is retried. Every change is committed on its own.

Claiming is recovery-safe. A runner claims a job with a conditional UPDATE that
also starts a lease and counts the attempt. If the runner dies, the lease runs
out and recover_abandoned_jobs() puts the job back to pending (or fails it once
the attempts are used up). A runner may only finish the attempt it claimed, in
the same transaction that saves the draft, so a run that lost its lease can't
save a second draft.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from src.ai.provider import ProviderConfigError, ProviderError, get_provider
from src.ai.source_prompt import SourceInput, generate_source_profile
from src.config import settings
from src.db import SessionLocal
from src.document_extraction import UnsupportedDocumentTypeError, extract_document
from src.models import (
    ClientProfile,
    ExtractedText,
    JobStatus,
    OnboardingJob,
    SourceDocument,
)
from src.profile_sources import save_source_profile
from src.storage import DocumentStorage, get_storage

log = logging.getLogger(__name__)

# Keep stored error messages short; the full traceback goes to the server log.
MAX_ERROR_LENGTH = 500


def run_onboarding_job(job_id: uuid.UUID, storage: DocumentStorage) -> None:
    """Run one job if it is pending and due. Used right after an upload.

    Never raises: every failure is recorded on the job.
    """
    # A session of its own: the request's session is closed once the response
    # has been sent, which is when background tasks run.
    with SessionLocal() as db:
        job = _claim(db, job_id)
        if job is not None:
            _execute(db, job, storage)


def run_next_job(storage: DocumentStorage) -> bool:
    """Claim and run the oldest due pending job. Returns False if there was none."""
    with SessionLocal() as db:
        # SKIP LOCKED: if another runner is claiming this row, take the next one.
        job_id = db.scalar(
            select(OnboardingJob.id)
            .where(OnboardingJob.status == JobStatus.PENDING, _is_due())
            .order_by(OnboardingJob.created_at, OnboardingJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job_id is None:
            db.rollback()
            return False
        job = _claim(db, job_id)
        if job is not None:
            _execute(db, job, storage)
        return True


def recover_abandoned_jobs() -> int:
    """Requeue running jobs whose lease ran out; fail them if out of attempts.

    A running job with an expired lease means its runner stopped (crash,
    restart, or a run longer than JOB_TIMEOUT_SECONDS). Returns how many
    jobs were recovered.
    """
    now = _now()
    abandoned = (
        OnboardingJob.status == JobStatus.RUNNING,
        OnboardingJob.lease_expires_at < now,
    )
    max_attempts = 1 + settings.JOB_RETRY_ATTEMPTS
    with SessionLocal() as db:
        requeued = db.execute(
            update(OnboardingJob)
            .where(*abandoned, OnboardingJob.attempts < max_attempts)
            .values(
                status=JobStatus.PENDING,
                lease_expires_at=None,
                next_attempt_at=now,
                error="Previous attempt stopped before finishing",
            )
        ).rowcount
        failed = db.execute(
            update(OnboardingJob)
            .where(*abandoned, OnboardingJob.attempts >= max_attempts)
            .values(
                status=JobStatus.FAILED,
                lease_expires_at=None,
                finished_at=now,
                error="Job stopped before finishing and has no attempts left",
            )
        ).rowcount
        db.commit()
    if requeued or failed:
        log.warning(
            "Recovered abandoned onboarding jobs: %s requeued, %s failed",
            requeued,
            failed,
        )
    return requeued + failed


def start_worker(
    storage_factory: Callable[[], DocumentStorage] = get_storage,
) -> Callable[[], None]:
    """Start the single background worker thread; returns a function to stop it.

    Each round recovers abandoned jobs, then runs due pending jobs one at a
    time until none are left, then waits JOB_POLL_SECONDS.
    """
    stop = threading.Event()

    def loop() -> None:
        storage = storage_factory()
        while not stop.is_set():
            try:
                recover_abandoned_jobs()
                while not stop.is_set() and run_next_job(storage):
                    pass
            except Exception:
                # e.g. the database is briefly unreachable; try again next round.
                log.exception("Onboarding worker round failed")
            stop.wait(settings.JOB_POLL_SECONDS)

    thread = threading.Thread(target=loop, name="onboarding-worker", daemon=True)
    thread.start()

    def stop_worker() -> None:
        stop.set()
        thread.join(timeout=settings.JOB_POLL_SECONDS + 5)

    return stop_worker


def _claim(db: Session, job_id: uuid.UUID) -> OnboardingJob | None:
    """Move a due pending job to running, or return None if it isn't one.

    The conditional UPDATE means two runners can't both claim the same attempt.
    """
    now = _now()
    claimed = db.execute(
        update(OnboardingJob)
        .where(
            OnboardingJob.id == job_id,
            OnboardingJob.status == JobStatus.PENDING,
            _is_due(now),
        )
        .values(
            status=JobStatus.RUNNING,
            attempts=OnboardingJob.attempts + 1,
            started_at=now,
            lease_expires_at=now + timedelta(seconds=settings.JOB_TIMEOUT_SECONDS),
            next_attempt_at=None,
        )
    ).rowcount
    db.commit()
    if not claimed:
        # Normal when the worker and the upload's task race for a new job.
        log.debug("Onboarding job %s is not pending and due; skipped", job_id)
        return None
    return db.get(OnboardingJob, job_id)


def _execute(db: Session, job: OnboardingJob, storage: DocumentStorage) -> None:
    """Run a claimed job and record the outcome of this attempt."""
    job_id, attempt = job.id, job.attempts
    try:
        extract_document(job.client_id, job.document_id, db, storage)
        sources = _client_sources(db, job.client_id)
        # The model call happens outside any transaction, so no row locks
        # are held while a local model takes its time.
        draft = generate_source_profile(sources, get_provider())
        profile = _profile_for(db, job.client_id)
        version = save_source_profile(db, profile.id, draft)
        # Same transaction as the draft: if this attempt lost its claim, the
        # rollback discards the draft too, so retries can't duplicate it.
        if not _finish_attempt(
            db,
            job_id,
            attempt,
            status=JobStatus.SUCCEEDED,
            result_version_id=version.id,
            error=None,
            finished_at=_now(),
        ):
            db.rollback()
            log.warning("Onboarding job %s lost its claim; draft discarded", job_id)
            return
        db.commit()
    except Exception as error:
        db.rollback()
        log.exception("Onboarding job %s attempt %s failed", job_id, attempt)
        _record_failure(db, job_id, attempt, error)


def _finish_attempt(db: Session, job_id: uuid.UUID, attempt: int, **values) -> bool:
    """Update the job only if this attempt still holds the claim."""
    return bool(
        db.execute(
            update(OnboardingJob)
            .where(
                OnboardingJob.id == job_id,
                OnboardingJob.status == JobStatus.RUNNING,
                OnboardingJob.attempts == attempt,
            )
            .values(lease_expires_at=None, **values)
        ).rowcount
    )


def _record_failure(
    db: Session, job_id: uuid.UUID, attempt: int, error: Exception
) -> None:
    """Schedule a retry for temporary failures with attempts left, else fail."""
    message = _describe(error)[:MAX_ERROR_LENGTH]
    now = _now()
    if _is_retryable(error) and attempt <= settings.JOB_RETRY_ATTEMPTS:
        delay = timedelta(seconds=settings.JOB_RETRY_DELAY_SECONDS * attempt)
        values = {
            "status": JobStatus.PENDING,
            "next_attempt_at": now + delay,
            "error": message,
        }
    else:
        values = {"status": JobStatus.FAILED, "finished_at": now, "error": message}
    try:
        if not _finish_attempt(db, job_id, attempt, **values):
            log.warning("Onboarding job %s lost its claim before failing", job_id)
        db.commit()
    except Exception:
        # Most likely the database itself is down. The lease will run out and
        # recover_abandoned_jobs() will pick the job up again.
        db.rollback()
        log.exception("Could not record failure for onboarding job %s", job_id)


def _is_retryable(error: Exception) -> bool:
    """Temporary problems worth another try; bad input or output is not."""
    if isinstance(error, ProviderConfigError):
        return False
    if isinstance(error, ProviderError):
        return True  # unreachable, timed out, or an error reply from the model
    return isinstance(error, OSError) and not isinstance(error, FileNotFoundError)


def _is_due(now: datetime | None = None):
    now = now or _now()
    return or_(
        OnboardingJob.next_attempt_at.is_(None), OnboardingJob.next_attempt_at <= now
    )


def _client_sources(db: Session, client_id: uuid.UUID) -> list[SourceInput]:
    """Every extracted document for the client, so transcript and intake combine."""
    rows = db.execute(
        select(SourceDocument, ExtractedText)
        .join(ExtractedText, ExtractedText.document_id == SourceDocument.id)
        .where(SourceDocument.client_id == client_id)
        .order_by(SourceDocument.uploaded_at, SourceDocument.id)
    ).all()
    sources = [
        SourceInput(
            document_id=str(document.id),
            # Same fallback as profile_sources for documents uploaded without a kind.
            kind=document.kind.value if document.kind else "transcript",
            text=extracted.text,
        )
        for document, extracted in rows
        if extracted.text.strip()  # SourceInput rejects empty text
    ]
    if not sources:
        raise ValueError("No extracted text is available for this client")
    return sources


def _profile_for(db: Session, client_id: uuid.UUID) -> ClientProfile:
    """The client's newest profile, created if the client has none yet."""
    profile = db.scalar(
        select(ClientProfile)
        .where(ClientProfile.client_id == client_id)
        .order_by(ClientProfile.created_at.desc(), ClientProfile.id.desc())
        .limit(1)
    )
    if profile is None:
        profile = ClientProfile(client_id=client_id)
        db.add(profile)
        db.flush()
    return profile


def _describe(error: Exception) -> str:
    """A short reason safe to show in the app (no model output or file paths)."""
    if isinstance(error, ProviderConfigError):
        return f"AI provider is not configured: {error}"
    if isinstance(error, ProviderError):
        return f"AI provider failed: {type(error).__name__}"
    if isinstance(error, ValidationError):
        return "Agent reply did not match the client profile format"
    if isinstance(error, UnsupportedDocumentTypeError):
        return str(error)
    if isinstance(error, FileNotFoundError):
        return "Stored document file is unavailable"
    if isinstance(error, OSError):
        return "Document storage is unavailable"
    if isinstance(error, (ValueError, LookupError)):
        return f"Draft could not be saved: {error}"
    return "Unexpected error; see server logs"


def _now() -> datetime:
    return datetime.now(timezone.utc)
