"""
Thin provider adapter pattern for AI model providers.

Abstracts model calls to support switching between Ollama, Anthropic, OpenAI, etc.
without coupling business logic to any specific provider.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel


class ModelRequest(BaseModel):
    """Standard request contract for all providers."""

    prompt: str
    schema: dict[str, Any] | None = None  # For structured output
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 300


class ModelResponse(BaseModel):
    """Standard response contract for all providers."""

    content: str
    provider: str
    model: str
    tokens_used: int
    cost_estimate: float  # Rough estimate in USD


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def call(self, request: ModelRequest) -> ModelResponse:
        """Execute a model call and return structured response."""

    @abstractmethod
    def validate_credentials(self) -> bool:
        """Check if provider credentials are configured."""


class OllamaProvider(AIProvider):
    """Local Ollama provider adapter."""

    def __init__(
        self, base_url: str = "http://localhost:11434", model_name: str = "llama2"
    ):
        self.base_url = base_url
        self.model_name = model_name

    def validate_credentials(self) -> bool:
        """Ollama doesn't need API keys; just check connectivity."""
        try:
            httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return True
        except httpx.RequestError:
            return False

    async def call(self, request: ModelRequest) -> ModelResponse:
        """Call Ollama API with structured output support."""
        async with httpx.AsyncClient(timeout=request.timeout) as client:
            payload = {
                "model": self.model_name,
                "prompt": request.prompt,
                "stream": False,
                "temperature": request.temperature,
            }

            if request.schema:
                # Ollama supports JSON schema constraints (experimental)
                payload["format"] = "json"

            response = await client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()

            data = response.json()

            return ModelResponse(
                content=data.get("response", ""),
                provider="ollama",
                model=self.model_name,
                tokens_used=data.get("eval_count", 0),
                cost_estimate=0.0,  # Local inference = no cost
            )


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider adapter."""

    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"

    def validate_credentials(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key and len(self.api_key) > 10)

    async def call(self, request: ModelRequest) -> ModelResponse:
        """Call Anthropic API."""
        async with httpx.AsyncClient(timeout=request.timeout) as client:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }

            payload = {
                "model": self.model,
                "max_tokens": request.max_tokens,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": request.temperature,
            }

            if request.schema:
                # Claude supports structured outputs via system prompt
                system_prompt = f"Return valid JSON matching this schema: {json.dumps(request.schema)}"
                payload["system"] = system_prompt

            response = await client.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            tokens_used = data.get("usage", {}).get("output_tokens", 0)

            # Rough cost estimate: Claude 3 Sonnet ~$3/1M input, $15/1M output
            cost = (tokens_used * 15) / 1_000_000

            return ModelResponse(
                content=data["content"][0]["text"],
                provider="anthropic",
                model=self.model,
                tokens_used=tokens_used,
                cost_estimate=cost,
            )


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider adapter."""

    def __init__(self, api_key: str, model: str = "gpt-4-turbo"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"

    def validate_credentials(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key and self.api_key.startswith("sk-"))

    async def call(self, request: ModelRequest) -> ModelResponse:
        """Call OpenAI API."""
        async with httpx.AsyncClient(timeout=request.timeout) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }

            payload = {
                "model": self.model,
                "max_tokens": request.max_tokens,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": request.temperature,
            }

            if request.schema:
                # OpenAI supports structured outputs
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "structured_output",
                        "schema": request.schema,
                    },
                }

            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            tokens_used = data.get("usage", {}).get("completion_tokens", 0)

            # Rough cost estimate: GPT-4 Turbo ~$10/1M input, $30/1M output
            cost = (tokens_used * 30) / 1_000_000

            return ModelResponse(
                content=data["choices"][0]["message"]["content"],
                provider="openai",
                model=self.model,
                tokens_used=tokens_used,
                cost_estimate=cost,
            )


class ProviderFactory:
    """Factory to instantiate the correct provider based on configuration."""

    @staticmethod
    def create(provider_name: str, **kwargs: Any) -> AIProvider:
        """
        Create a provider instance.

        Args:
            provider_name: 'ollama', 'anthropic', or 'openai'
            **kwargs: Provider-specific configuration

        Returns:
            Configured AIProvider instance

        Raises:
            ValueError: If provider_name is unknown
        """
        providers = {
            "ollama": OllamaProvider,
            "anthropic": AnthropicProvider,
            "openai": OpenAIProvider,
        }

        if provider_name not in providers:
            msg = (
                f"Unknown provider: {provider_name}. "
                f"Choose from {list(providers.keys())}"
            )
            raise ValueError(msg)

        return providers[provider_name](**kwargs)
