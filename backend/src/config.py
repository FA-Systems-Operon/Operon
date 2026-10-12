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
    # Folder where uploaded documents are saved. Relative paths are resolved from
    # the working directory (/app in Docker, so the default is /app/storage).
    STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
    # Uploads larger than this are rejected with 413. Default: 20 MB.
    MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))


settings = Settings()
