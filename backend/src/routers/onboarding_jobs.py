"""Start and check onboarding-agent drafts for a client (#36).

The upload page uploads the transcript and the intake answers one after the
other, then calls POST here with both document IDs. Only then does a job start,
so the agent never drafts from one file alone.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db import get_db
from src.models import Client, DocumentKind, JobStatus, OnboardingJob, SourceDocument
from src.onboarding_jobs import run_onboarding_job
from src.schemas import OnboardingJobIn, OnboardingJobOut
from src.storage import DocumentStorage, get_storage

router = APIRouter(
    prefix="/api/v1/clients/{client_id}/onboarding-jobs", tags=["onboarding-jobs"]
)

DbSession = Annotated[Session, Depends(get_db)]
Storage = Annotated[DocumentStorage, Depends(get_storage)]


@router.post("", response_model=OnboardingJobOut, status_code=status.HTTP_201_CREATED)
def start_onboarding_job(
    client_id: uuid.UUID,
    body: OnboardingJobIn,
    db: DbSession,
    storage: Storage,
    background_tasks: BackgroundTasks,
    response: Response,
) -> OnboardingJob:
    """Start a draft from one transcript and one intake document of this client.

    Returns 201 with a new pending job. Asking again for the same pair returns
    the existing job with 200 instead of starting a second draft; a job that
    failed is queued again.
    """
    if db.get(Client, client_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    for document_id, kind in (
        (body.transcript_document_id, DocumentKind.TRANSCRIPT),
        (body.intake_document_id, DocumentKind.INTAKE),
    ):
        # Scoped to the client: another client's document is "not found" too.
        document = db.scalar(
            select(SourceDocument).where(
                SourceDocument.id == document_id,
                SourceDocument.client_id == client_id,
            )
        )
        if document is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"{kind.value.capitalize()} not found"
            )
        if document.kind != kind:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"{kind.value}_document_id must be a {kind.value} document",
            )

    job = _job_for_pair(db, body)
    if job is None:
        job = OnboardingJob(
            client_id=client_id,
            transcript_document_id=body.transcript_document_id,
            intake_document_id=body.intake_document_id,
        )
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            # A concurrent request for the same pair won the race.
            db.rollback()
            job = _job_for_pair(db, body)
            response.status_code = status.HTTP_200_OK
            return job
    else:
        response.status_code = status.HTTP_200_OK
        if job.status != JobStatus.FAILED:
            return job
        _requeue(job)
        db.commit()
    db.refresh(job)
    background_tasks.add_task(run_onboarding_job, job.id, storage)
    return job


@router.get("/{job_id}", response_model=OnboardingJobOut)
def get_onboarding_job(
    client_id: uuid.UUID, job_id: uuid.UUID, db: DbSession
) -> OnboardingJob:
    """Return one of this client's onboarding jobs."""
    job = db.scalar(
        select(OnboardingJob).where(
            OnboardingJob.id == job_id, OnboardingJob.client_id == client_id
        )
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Onboarding job not found")
    return job


def _job_for_pair(db: Session, body: OnboardingJobIn) -> OnboardingJob | None:
    return db.scalar(
        select(OnboardingJob).where(
            OnboardingJob.transcript_document_id == body.transcript_document_id,
            OnboardingJob.intake_document_id == body.intake_document_id,
        )
    )


def _requeue(job: OnboardingJob) -> None:
    """Give a failed job a fresh start."""
    job.status = JobStatus.PENDING
    job.error = None
    job.started_at = None
    job.finished_at = None
