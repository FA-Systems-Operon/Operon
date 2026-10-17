"""ModelProvider implementation for Ollama's HTTP API."""

import time

import httpx

from src.ai.provider import (
    ModelResponse,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)

# Shared by every provider built without its own client, so building one per
# request (as get_provider() callers do) doesn't open a new connection pool each time.
_default_client = httpx.Client()


class OllamaProvider:
    """Sends prompts to a local Ollama server."""

    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 120,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        # Tests pass a client backed by httpx.MockTransport instead of the network.
        self.client = client or _default_client

    def generate(
        self, prompt: str, *, system: str | None = None, json_output: bool = False
    ) -> ModelResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Fixed temperature and seed keep runs reproducible (US 2.1 risk section).
            "options": {"temperature": 0, "seed": 42},
        }
        if system is not None:
            payload["system"] = system
        if json_output:
            payload["format"] = "json"

        start = time.perf_counter()
        body = self._request("POST", "/api/generate", json=payload)
        duration_ms = round((time.perf_counter() - start) * 1000)

        try:
            text = body["response"]
        except (KeyError, TypeError) as error:
            raise ProviderResponseError("Ollama reply has no 'response' key") from error

        return ModelResponse(
            text=text, provider=self.name, model=self.model, duration_ms=duration_ms
        )

    def list_models(self, *, timeout: float | None = None) -> list[str]:
        """Names of the models pulled on this server (GET /api/tags)."""
        body = self._request("GET", "/api/tags", timeout=timeout)
        try:
            return [model["name"] for model in body.get("models", [])]
        except (AttributeError, KeyError, TypeError) as error:
            raise ProviderResponseError(
                "Ollama returned an unexpected model list"
            ) from error

    def _request(
        self, method: str, path: str, *, timeout: float | None = None, **kwargs
    ):
        """Send one request and return its JSON body, mapping httpx errors to ours."""
        timeout = self.timeout if timeout is None else timeout
        try:
            response = self.client.request(
                method, f"{self.base_url}{path}", timeout=timeout, **kwargs
            )
            response.raise_for_status()
        # TimeoutException is a subclass of HTTPError, so it must come first.
        except httpx.TimeoutException as error:
            raise ProviderTimeout(
                f"Ollama at {self.base_url} did not answer within {timeout}s"
            ) from error
        except httpx.ConnectError as error:
            raise ProviderUnavailable(
                f"Cannot reach Ollama at {self.base_url}"
            ) from error
        except httpx.HTTPStatusError as error:
            raise ProviderResponseError(
                f"Ollama rejected {path} with status {error.response.status_code}",
                status_code=error.response.status_code,
                body=error.response.text,
            ) from error
        except httpx.HTTPError as error:
            raise ProviderUnavailable(
                f"Request to Ollama at {self.base_url} failed: {type(error).__name__}"
            ) from error

        try:
            return response.json()
        except ValueError as error:
            raise ProviderResponseError(f"Ollama {path} reply is not JSON") from error
