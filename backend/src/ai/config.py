"""
AI provider configuration and factory initialization.
Reads environment variables and instantiates the active provider.
"""

import os

from src.ai.provider import AIProvider, ProviderFactory


def get_active_provider() -> AIProvider:
    """
    Load and return the configured AI provider.

    Environment variables:
    - AI_PROVIDER: 'ollama', 'anthropic', or 'openai' (default: ollama)
    - OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434)
    - OLLAMA_MODEL_NAME: Model to use in Ollama (default: llama2)
    - ANTHROPIC_API_KEY: API key for Anthropic (if provider=anthropic)
    - OPENAI_API_KEY: API key for OpenAI (if provider=openai)
    """
    provider_name = os.getenv("AI_PROVIDER", "ollama").lower()

    if provider_name == "ollama":
        provider = ProviderFactory.create(
            "ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model_name=os.getenv("OLLAMA_MODEL_NAME", "llama2"),
        )

    elif provider_name == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            msg = "ANTHROPIC_API_KEY environment variable is required for Anthropic provider"
            raise ValueError(msg)
        provider = ProviderFactory.create("anthropic", api_key=api_key)

    elif provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            msg = "OPENAI_API_KEY environment variable is required for OpenAI provider"
            raise ValueError(msg)
        provider = ProviderFactory.create("openai", api_key=api_key)

    else:
        msg = f"Unknown AI_PROVIDER: {provider_name}"
        raise ValueError(msg)

    # Validate credentials
    if not provider.validate_credentials():
        msg = f"Cannot validate credentials for {provider_name}. Check configuration."
        raise RuntimeError(msg)

    return provider
