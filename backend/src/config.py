"""Application configuration."""

import os


class Settings:
    """Application settings from environment variables."""

    def __init__(self):
        self.DEBUG = os.getenv("DEBUG", "true").lower() == "true"
        # DEBUG, INFO, WARNING, ERROR or CRITICAL. Checked at startup.
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
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
        # Onboarding jobs (#37). The worker polls for pending jobs and recovers
        # jobs whose runner stopped (crash, restart) once their lease runs out.
        self.BACKGROUND_WORKER_ENABLED = (
            os.getenv("BACKGROUND_WORKER_ENABLED", "true").lower() == "true"
        )
        self.JOB_POLL_SECONDS = float(os.getenv("JOB_POLL_SECONDS", "5"))
        # How long one run may take before it counts as abandoned. Keep this
        # longer than OLLAMA_TIMEOUT_SECONDS.
        self.JOB_TIMEOUT_SECONDS = float(os.getenv("JOB_TIMEOUT_SECONDS", "600"))
        # Retries after the first attempt, for temporary failures only.
        self.JOB_RETRY_ATTEMPTS = int(os.getenv("JOB_RETRY_ATTEMPTS", "3"))
        # Wait before retry N is N times this (30s, 60s, 90s, ...).
        self.JOB_RETRY_DELAY_SECONDS = float(os.getenv("JOB_RETRY_DELAY_SECONDS", "30"))


settings = Settings()
