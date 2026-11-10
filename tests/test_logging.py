"""Leveled logging, and no document text in the logs.

The end-to-end tests upload documents containing a marker string, run the
onboarding job through success and failure, and check the marker never shows
up in the formatted log output at DEBUG (the most verbose level).
"""

import io
import json
import logging
import sys

import pytest
from pydantic import BaseModel, ValidationError
from tests.test_onboarding_jobs import (
    INTAKE,
    TRANSCRIPT,
    SourceAwareProvider,
    combined_draft,
    get_job,
    start_draft,
)

from src.ai.provider import ProviderResponseError, ProviderTimeout
from src.config import Settings
from src.logging_config import (
    LOG_FORMAT,
    WITHHELD,
    SafeFormatter,
    configure_logging,
    describe_exception,
    format_exception_safely,
    parse_level,
)

MARKER = "ZEBRA-SECRET-4242"


@pytest.fixture
def log_output():
    """Everything logged during the test, formatted as production formats it."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SafeFormatter(LOG_FORMAT))
    root = logging.getLogger()
    previous = root.level
    # Only this handler formats, so a leak can't hide behind the app handler
    # having already cached a safe traceback on the record.
    app_handlers = [h for h in root.handlers if getattr(h, "_operon", False)]
    for app_handler in app_handlers:
        root.removeHandler(app_handler)
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield stream
    root.removeHandler(handler)
    for app_handler in app_handlers:
        root.addHandler(app_handler)
    root.setLevel(previous)


def _formatted(error: Exception) -> str:
    try:
        raise error
    except Exception:  # noqa: BLE001 - any error under test
        return format_exception_safely(sys.exc_info())


class _Strict(BaseModel):
    value: int


def _validation_error(value) -> ValidationError:
    try:
        _Strict.model_validate({"value": value})
    except ValidationError as error:
        return error
    raise AssertionError("expected a ValidationError")


# --- Levels -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("debug", "DEBUG"), (" Warning ", "WARNING"), (None, "INFO"), ("", "INFO")],
)
def test_levels_are_case_insensitive_with_info_as_default(value, expected):
    assert parse_level(value) == expected


def test_unknown_level_is_rejected():
    with pytest.raises(ValueError, match="Unknown LOG_LEVEL 'verbose'"):
        parse_level("verbose")


def test_settings_read_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")
    assert Settings().LOG_LEVEL == "WARNING"
    monkeypatch.delenv("LOG_LEVEL")
    assert Settings().LOG_LEVEL == "INFO"


def test_configure_logging_sets_the_level_and_adds_one_handler():
    root = logging.getLogger()
    previous = root.level
    try:
        configure_logging("ERROR")
        configure_logging("WARNING")
        assert root.level == logging.WARNING
        ours = [h for h in root.handlers if getattr(h, "_operon", False)]
        assert len(ours) == 1
        assert isinstance(ours[0].formatter, SafeFormatter)
    finally:
        root.setLevel(previous)


def test_server_logger_handlers_also_withhold_messages():
    server = logging.getLogger("uvicorn.error")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    server.addHandler(handler)
    try:
        configure_logging("INFO")
        try:
            raise ValueError(MARKER)
        except ValueError:
            server.exception("Exception in ASGI application")
    finally:
        server.removeHandler(handler)
    output = stream.getvalue()
    assert "Exception in ASGI application" in output
    assert "ValueError: " + WITHHELD in output
    assert MARKER not in output


# --- Exception formatting ---------------------------------------------------


def test_validation_errors_lose_their_quoted_input():
    error = _validation_error(MARKER)
    assert MARKER in str(error)  # the reason this module exists
    described = describe_exception(error)
    assert MARKER not in described
    assert "ValidationError" in described


def test_our_own_error_messages_are_kept():
    assert describe_exception(ProviderTimeout("Ollama did not answer within 5s")) == (
        "src.ai.provider.ProviderTimeout: Ollama did not answer within 5s"
    )


def test_provider_reply_body_is_never_printed():
    error = ProviderResponseError("Ollama rejected /api/generate", body=MARKER)
    assert MARKER not in _formatted(error)


def test_traceback_keeps_frames_but_withholds_chained_messages():
    def inner():
        raise KeyError(MARKER)

    def outer():
        try:
            inner()
        except KeyError as error:
            raise RuntimeError(f"wrapped {MARKER}") from error

    try:
        outer()
    except RuntimeError:
        output = format_exception_safely(sys.exc_info())
    assert MARKER not in output
    assert "in inner" in output and "in outer" in output
    assert f"KeyError: {WITHHELD}" in output
    assert f"RuntimeError: {WITHHELD}" in output


def test_a_traceback_cached_by_another_formatter_is_not_reused():
    try:
        raise ValueError(MARKER)
    except ValueError:
        record = logging.getLogger("src.test").makeRecord(
            "src.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )
    assert MARKER in logging.Formatter().format(record)  # caches exc_text
    assert MARKER not in SafeFormatter().format(record)


def test_exceptions_passed_as_arguments_are_scrubbed(log_output):
    logging.getLogger("src.test").error("Failed: %s", ValueError(MARKER))
    assert "Failed: ValueError: " + WITHHELD in log_output.getvalue()
    assert MARKER not in log_output.getvalue()


# --- End to end: no document text in logs ------------------------------------


def test_successful_job_logs_progress_without_document_text(
    client, demo_client, monkeypatch, log_output
):
    provider = SourceAwareProvider(combined_draft)
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: provider)

    *_, job = start_draft(
        client,
        demo_client,
        transcript=TRANSCRIPT + f"Note: {MARKER}\n",
        intake=INTAKE + f"Code: {MARKER}\n",
    )

    assert get_job(client, demo_client, job)["status"] == "succeeded"
    output = log_output.getvalue()
    assert "Stored document" in output
    assert "Extracted document" in output
    assert "attempt 1 succeeded" in output
    assert MARKER not in output
    assert "Maya Chen" not in output


def test_failed_job_logs_traceback_without_document_text(
    client, demo_client, monkeypatch, log_output
):
    # The model echoes document text in a reply that fails validation, so the
    # resulting ValidationError quotes it.
    def bad_reply(ids):
        return {"name": MARKER, "needs": MARKER, "source_references": MARKER}

    provider = SourceAwareProvider(bad_reply)
    monkeypatch.setattr("src.onboarding_jobs.get_provider", lambda: provider)

    *_, job = start_draft(
        client, demo_client, transcript=TRANSCRIPT + f"Note: {MARKER}\n"
    )

    assert get_job(client, demo_client, job)["status"] == "failed"
    output = log_output.getvalue()
    assert "attempt 1 failed" in output
    assert "Traceback (most recent call last)" in output
    assert "ValidationError" in output
    assert MARKER not in output


def test_model_call_debug_log_has_sizes_only(log_output):
    import httpx

    from src.ai.ollama import OllamaProvider

    def reply(request):
        return httpx.Response(200, json={"response": json.dumps({"x": MARKER})})

    provider = OllamaProvider(
        base_url="http://ollama.test",
        model="m",
        client=httpx.Client(transport=httpx.MockTransport(reply)),
    )
    provider.generate(f"Summarise: {MARKER}")

    output = log_output.getvalue()
    assert "Ollama m replied" in output
    assert "chars" in output
    assert MARKER not in output
