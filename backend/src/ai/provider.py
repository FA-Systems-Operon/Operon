"""The provider interface, its response type and errors, and get_provider()."""

from dataclasses import dataclass
from typing import Protocol

from src.config import settings


@dataclass(frozen=True)
class ModelResponse:
    """One model reply, plus the metadata we save alongside it."""

    text: str
    provider: str
    model: str
    duration_ms: int


class ProviderError(Exception):
    """Base class for every provider failure, so callers never see httpx errors."""


class ProviderUnavailable(ProviderError):
    """The provider could not be reached."""


class ProviderTimeout(ProviderError):
    """The provider did not answer in time."""


class ProviderResponseError(ProviderError):
    """The provider answered, but with an error status or an unusable body."""

    def __init__(
        self, message: str, *, status_code: int | None = None, body: str | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class ProviderConfigError(ProviderError):
    """The settings don't describe a usable provider (unknown name, no model)."""


class ModelProvider(Protocol):
    """Anything that can turn a prompt into a ModelResponse."""

    def generate(
        self, prompt: str, *, system: str | None = None, json_output: bool = False
    ) -> ModelResponse: ...


def get_provider() -> ModelProvider:
    """Build the provider selected by AI_PROVIDER in the settings."""
    # Imported here because ollama.py imports this module for the error types.
    from src.ai.ollama import OllamaProvider

    name = settings.AI_PROVIDER.strip().lower()
    if name != "ollama":
        raise ProviderConfigError(
            f"Unknown AI_PROVIDER {settings.AI_PROVIDER!r}. Supported: 'ollama'."
        )
    if not settings.OLLAMA_MODEL:
        raise ProviderConfigError(
            "OLLAMA_MODEL is not set. Add it to your .env (see .env.example)."
        )
    return OllamaProvider(
        base_url=settings.OLLAMA_BASE_URL,
        model=settings.OLLAMA_MODEL,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )
