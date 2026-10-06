import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Operon"
    debug: bool = False

    # AI Provider Configuration
    ai_provider: str = os.getenv("AI_PROVIDER", "ollama")

    # Ollama (local model serving)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    ollama_model_name: str = os.getenv("OLLAMA_MODEL_NAME", "llama2")

    # Cloud Providers (placeholder for future)
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://operon_user:[REDACTED]@postgres:5432/operon_dev",
    )

    # Background Workers
    background_worker_enabled: bool = (
        os.getenv("BACKGROUND_WORKER_ENABLED", "true").lower() == "true"
    )
    max_concurrent_jobs: int = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))
    job_timeout_seconds: int = int(os.getenv("JOB_TIMEOUT_SECONDS", "300"))
    job_retry_attempts: int = int(os.getenv("JOB_RETRY_ATTEMPTS", "3"))

    # Budget
    max_budget_cents: int = int(os.getenv("MAX_BUDGET_CENTS", "100"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
