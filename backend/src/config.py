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


settings = Settings()
