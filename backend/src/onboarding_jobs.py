"""Run the onboarding agent on a client's transcript and intake answers (#36).

Uploading a file only saves it. Once both files are in, the client calls
POST /api/v1/clients/{client_id}/onboarding-jobs with the two document IDs (the
upload page does this from its onUploaded hook). That saves a pending
OnboardingJob pinned to exactly those two documents, then schedules
run_onboarding_job as a FastAPI background task. Each status change is
committed on its own so callers can watch progress:

    pending -> running -> succeeded | failed

Background tasks run inside the API process, so a crash or restart can leave a
job pending or running. Picking those up again and retrying is #37.
"""

import logging
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.ai.provider import ProviderConfigError, ProviderError, get_provider
from src.ai.source_prompt import SourceInput, generate_source_profile
from src.db import SessionLocal
from src.document_extraction import UnsupportedDocumentTypeError, extract_document
from src.models import (
    ClientProfile,
    DocumentKind,
    ExtractedText,
    JobStatus,
    OnboardingJob,
    SourceDocument,
)
from src.profile_sources import save_source_profile
from src.storage import DocumentStorage

log = logging.getLogger(__name__)

# Keep stored error messages short; the full traceback goes to the server log.
MAX_ERROR_LENGTH = 500


def run_onboarding_job(job_id: uuid.UUID, storage: DocumentStorage) -> None:
    """Extract both files, run the agent on exactly those two and save a draft.

    Never raises: every failure is recorded on the job as status "failed".
    """
    # A session of its own: the request's session is closed once the response
    # has been sent, which is when background tasks run.
    with SessionLocal() as db:
        job = _claim(db, job_id)
        if job is None:
            return
        try:
            for document_id in _document_ids(job):
                # Reuses text that was already extracted.
                extract_document(job.client_id, document_id, db, storage)
            sources = _job_sources(db, job)
            # The model call happens outside any transaction, so no row locks
            # are held while a local model takes its time.
            draft = generate_source_profile(sources, get_provider())
            profile = _profile_for(db, job.client_id)
            version = save_source_profile(db, profile.id, draft)
            job.status = JobStatus.SUCCEEDED
            job.result_version_id = version.id
            job.finished_at = _now()
            db.commit()
        except Exception as error:
            db.rollback()
            log.exception("Onboarding job %s failed", job_id)
            _mark_failed(db, job_id, _describe(error))


def _claim(db: Session, job_id: uuid.UUID) -> OnboardingJob | None:
    """Move a pending job to running, or return None if it isn't pending.

    The conditional UPDATE means two runners can't both start the same job.
    """
    claimed = db.execute(
        update(OnboardingJob)
        .where(OnboardingJob.id == job_id, OnboardingJob.status == JobStatus.PENDING)
        .values(status=JobStatus.RUNNING, started_at=_now())
    ).rowcount
    db.commit()
    if not claimed:
        log.warning("Onboarding job %s is missing or not pending; skipped", job_id)
        return None
    return db.get(OnboardingJob, job_id)


def _document_ids(job: OnboardingJob) -> tuple[uuid.UUID, uuid.UUID]:
    return job.transcript_document_id, job.intake_document_id


def _job_sources(db: Session, job: OnboardingJob) -> list[SourceInput]:
    """The job's transcript and intake text, and nothing else the client has.

    Both must have text; a draft from only one of them would be incomplete.
    """
    rows = db.execute(
        select(SourceDocument, ExtractedText)
        .join(ExtractedText, ExtractedText.document_id == SourceDocument.id)
        .where(
            SourceDocument.id.in_(_document_ids(job)),
            SourceDocument.client_id == job.client_id,
        )
    ).all()
    texts = {document.id: (document, extracted.text) for document, extracted in rows}
    sources = []
    for document_id, kind in (
        (job.transcript_document_id, DocumentKind.TRANSCRIPT),
        (job.intake_document_id, DocumentKind.INTAKE),
    ):
        document, text = texts.get(document_id, (None, ""))
        if document is None or document.kind != kind or not text.strip():
            raise ValueError(f"The {kind.value} has no extracted text")
        sources.append(
            SourceInput(document_id=str(document_id), kind=kind.value, text=text)
        )
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


def _mark_failed(db: Session, job_id: uuid.UUID, message: str) -> None:
    try:
        db.execute(
            update(OnboardingJob)
            .where(OnboardingJob.id == job_id)
            .values(
                status=JobStatus.FAILED,
                error=message[:MAX_ERROR_LENGTH],
                finished_at=_now(),
            )
        )
        db.commit()
    except Exception:
        # Most likely the database itself is down; the job stays "running"
        # until #37's recovery picks it up.
        db.rollback()
        log.exception("Could not record failure for onboarding job %s", job_id)


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
