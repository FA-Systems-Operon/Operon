"""Application configuration."""

import os


class Settings:
    """Application settings from environment variables."""

    DEBUG = os.getenv("DEBUG", "true").lower() == "true"
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://operon_user:[REDACTED]@postgres:5432/operon_dev",
    )
    AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")


settings = Settings()
