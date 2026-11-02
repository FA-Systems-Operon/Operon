"""Task #36: failure paths of the onboarding job that the upload flow rarely hits.

Every failure must end with a short, user-safe error on the job, and recording
the failure must never raise, even when the database is unavailable.
"""

import uuid

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import OperationalError

from src.ai.provider import (
    ProviderConfigError,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from src.document_extraction import UnsupportedDocumentTypeError
from src.models import JobStatus, OnboardingJob
from src.onboarding_jobs import _describe, _mark_failed, run_onboarding_job


class _Strict(BaseModel):
    value: int


def _validation_error() -> ValidationError:
    try:
        _Strict.model_validate({"value": "not a number"})
    except ValidationError as error:
        return error
    raise AssertionError("expected a ValidationError")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            ProviderConfigError("OLLAMA_MODEL is not set."),
            "AI provider is not configured: OLLAMA_MODEL is not set.",
        ),
        (ProviderUnavailable("refused"), "AI provider failed: ProviderUnavailable"),
        (ProviderTimeout("slow"), "AI provider failed: ProviderTimeout"),
        (
            ProviderResponseError("bad", status_code=500, body="secret body"),
            "AI provider failed: ProviderResponseError",
        ),
        (_validation_error(), "Agent reply did not match the client profile format"),
        (
            UnsupportedDocumentTypeError("Unsupported document type: .docx"),
            "Unsupported document type: .docx",
        ),
        (FileNotFoundError("/code/storage/a/b"), "Stored document file is unavailable"),
        (PermissionError("/code/storage/a/b"), "Document storage is unavailable"),
        (ValueError("Quote not found"), "Draft could not be saved: Quote not found"),
        (
            LookupError("Client profile not found"),
            "Draft could not be saved: Client profile not found",
        ),
        (RuntimeError("boom at 0x7f"), "Unexpected error; see server logs"),
    ],
)
def test_errors_are_described_without_internal_details(error, expected):
    assert _describe(error) == expected


def reload(db_session, job):
    db_session.expire_all()
    return db_session.get(OnboardingJob, job.id)


def test_missing_extracted_text_fails_the_job(
    db_session, storage, make_pair, monkeypatch
):
    job = make_pair()
    # Extraction "succeeds" without saving any text, so the set is incomplete.
    monkeypatch.setattr("src.onboarding_jobs.extract_document", lambda *a, **k: None)

    run_onboarding_job(job.id, storage)

    job = reload(db_session, job)
    assert job.status == JobStatus.FAILED
    assert job.error == "Draft could not be saved: The transcript has no extracted text"


def test_unexpected_error_fails_the_job_without_details(
    db_session, storage, make_pair, monkeypatch
):
    job = make_pair()

    def broken():
        raise RuntimeError("internal detail that must not reach the app")

    monkeypatch.setattr("src.onboarding_jobs.get_provider", broken)

    run_onboarding_job(job.id, storage)

    job = reload(db_session, job)
    assert job.status == JobStatus.FAILED
    assert job.error == "Unexpected error; see server logs"
    assert job.finished_at is not None


def test_storage_failure_fails_the_job(db_session, storage, make_pair, monkeypatch):
    job = make_pair()

    def unreadable(key):
        raise PermissionError(f"/code/storage/{key}")

    monkeypatch.setattr(storage, "read", unreadable)

    run_onboarding_job(job.id, storage)

    job = reload(db_session, job)
    assert job.status == JobStatus.FAILED
    assert job.error == "Document storage is unavailable"


def test_long_error_messages_are_truncated(db_session, storage, make_pair, monkeypatch):
    job = make_pair()
    monkeypatch.setattr("src.onboarding_jobs.extract_document", lambda *a, **k: None)
    monkeypatch.setattr("src.onboarding_jobs._describe", lambda error: "x" * 2000)

    run_onboarding_job(job.id, storage)

    assert reload(db_session, job).error == "x" * 500


class _UnavailableDatabase:
    """A session whose database has gone away."""

    def __init__(self):
        self.rolled_back = False

    def execute(self, *args, **kwargs):
        raise OperationalError("UPDATE onboarding_jobs", {}, Exception("gone"))

    def commit(self):
        raise AssertionError("commit must not be reached")

    def rollback(self):
        self.rolled_back = True


def test_failure_that_cannot_be_recorded_is_logged_not_raised(caplog):
    db = _UnavailableDatabase()

    _mark_failed(db, uuid.uuid4(), "AI provider failed: ProviderUnavailable")

    assert db.rolled_back
    assert "Could not record failure" in caplog.text
