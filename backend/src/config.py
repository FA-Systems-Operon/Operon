"""Application configuration."""

import os


class Settings:
    """Application settings from environment variables."""

    def __init__(self):
        self.DEBUG = os.getenv("DEBUG", "true").lower() == "true"
        self.DATABASE_URL = os.getenv("DATABASE_URL")
        self.AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")
        self.OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "").strip()
        # How long to wait for one model reply. Local models can be slow.
        self.OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
        # Folder where uploaded documents are saved. Relative paths are resolved
        # from the working directory (/code in Docker, so the default is /code/storage).
        self.STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
        # Uploads larger than this are rejected with 413. Default: 20 MB.
        self.MAX_UPLOAD_BYTES = int(
            os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))
        )


settings = Settings()
