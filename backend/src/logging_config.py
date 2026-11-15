"""Leveled logging for the backend, with no document text in the logs.

LOG_LEVEL (DEBUG, INFO, WARNING, ERROR, CRITICAL; default INFO) sets how much
the app logs. Get a logger with logging.getLogger(__name__) as usual.

Rule for log messages: log IDs, counts, sizes, durations, statuses and error
types. Never log document text, extracted text, prompts, model replies or
profile field values. Those come from client documents.

Exceptions are the easy place to break that rule by accident: a pydantic
ValidationError quotes the model reply it rejected, and SQLAlchemy errors quote
the SQL parameters (which can be extracted text). So the formatter here keeps
every traceback frame (file, line, function) and every exception type, but
drops exception messages unless the type is on SAFE_MESSAGE_TYPES, whose
messages this codebase writes itself and never fills with document text.
Exceptions passed as log arguments (log.error("... %s", error)) get the same
treatment.
"""

import logging
import sys
import traceback

from src.ai.provider import ProviderError
from src.document_extraction import DocumentNotFoundError, UnsupportedDocumentTypeError

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
DEFAULT_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# Our own exceptions with fixed, data-free messages. ProviderResponseError
# keeps the Ollama reply in .body, which is never printed; only str(error) is.
SAFE_MESSAGE_TYPES: tuple[type[BaseException], ...] = (
    ProviderError,
    DocumentNotFoundError,
    UnsupportedDocumentTypeError,
)

WITHHELD = "(message withheld: may contain document text)"

# Loggers that keep their own handlers instead of propagating to the root.
# Their unhandled-request tracebacks need the same protection.
_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")


def parse_level(value: str | None) -> str:
    """Normalise a LOG_LEVEL value, or raise ValueError for an unknown one."""
    level = (value or DEFAULT_LEVEL).strip().upper()
    if level not in LEVELS:
        raise ValueError(
            f"Unknown LOG_LEVEL {value!r}. Use one of: {', '.join(LEVELS)}."
        )
    return level


def describe_exception(error: BaseException) -> str:
    """Type name, plus the message only if the type is known to be safe."""
    name = type(error).__qualname__
    module = type(error).__module__
    if module not in ("builtins", "__main__"):
        name = f"{module}.{name}"
    if isinstance(error, SAFE_MESSAGE_TYPES):
        message = str(error)
        return f"{name}: {message}" if message else name
    return f"{name}: {WITHHELD}"


def format_exception_safely(exc_info) -> str:
    """A traceback like the standard one, minus unsafe exception messages."""
    error = exc_info[1]
    if error is None:
        return ""
    # Oldest first, following the same links Python's own traceback does.
    chain, seen = [], set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__suppress_context__:
            current = None
        else:
            current = current.__context__
    lines = []
    for index, item in enumerate(reversed(chain)):
        if index:
            lines.append("\nThe above exception was followed by the one below.\n\n")
        if item.__traceback__ is not None:
            lines.append("Traceback (most recent call last):\n")
            frames = traceback.extract_tb(item.__traceback__)
            lines.extend(traceback.format_list(frames))
        lines.append(describe_exception(item) + "\n")
    return "".join(lines).rstrip("\n")


class SafeFormatter(logging.Formatter):
    """Standard formatter that never prints unsafe exception messages."""

    def format(self, record: logging.LogRecord) -> str:
        _scrub_record(record)
        return super().format(record)

    def formatException(self, ei) -> str:
        return format_exception_safely(ei)


def _scrub_record(record: logging.LogRecord) -> None:
    """Make a record safe for any formatter before it is formatted.

    The traceback text is cached on the record (exc_text) by whichever handler
    formats it first, and every later handler reuses it. Always replacing it
    means a cached unsafe traceback is never reused here, and the safe one we
    leave behind is what later handlers print.
    """
    if record.exc_info:
        record.exc_text = format_exception_safely(record.exc_info)
    if isinstance(record.args, tuple) and any(
        isinstance(arg, BaseException) for arg in record.args
    ):
        record.args = tuple(
            describe_exception(arg) if isinstance(arg, BaseException) else arg
            for arg in record.args
        )
    elif isinstance(record.args, dict) and any(
        isinstance(arg, BaseException) for arg in record.args.values()
    ):
        record.args = {
            key: describe_exception(arg) if isinstance(arg, BaseException) else arg
            for key, arg in record.args.items()
        }


def _protect_handler(handler: logging.Handler) -> None:
    """Make an existing handler's formatter use the safe exception format."""
    formatter = handler.formatter or logging.Formatter()
    if isinstance(formatter, SafeFormatter):
        return
    original_format = formatter.format

    def safe_format(record: logging.LogRecord) -> str:
        _scrub_record(record)
        return original_format(record)

    # Instance attributes override the class methods Formatter.format calls.
    formatter.formatException = format_exception_safely
    formatter.format = safe_format
    handler.setFormatter(formatter)


def configure_logging(level: str = DEFAULT_LEVEL) -> None:
    """Send app logs to stderr at the given level. Safe to call more than once."""
    root = logging.getLogger()
    root.setLevel(parse_level(level))
    if not any(getattr(h, "_operon", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(SafeFormatter(LOG_FORMAT))
        handler._operon = True
        root.addHandler(handler)
    for name in _SERVER_LOGGERS:
        for handler in logging.getLogger(name).handlers:
            _protect_handler(handler)
