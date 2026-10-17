from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import src.models  # noqa: F401  (importing registers the tables on Base.metadata)
from src.ai import (
    ProviderConfigError,
    ProviderError,
    ProviderResponseError,
    get_provider,
)
from src.ai.ollama import OllamaProvider
from src.config import settings
from src.db import Base, engine
from src.routers import client_profiles, clients, documents, playbooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: create any tables that don't exist yet.

    create_all never alters existing tables, so schema changes need a DB reset
    until Alembic is added back (see backend/README.md).
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Operon API",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)
print(
    f"Ollama URL: {settings.OLLAMA_BASE_URL} | "
    f"model: {settings.OLLAMA_MODEL or '(OLLAMA_MODEL not set)'}",
    flush=True,
)

app.include_router(clients.router)
app.include_router(documents.router)
app.include_router(client_profiles.router)
app.include_router(playbooks.router)


@app.get("/health")
def health():
    return {"status": "ok"}


def check_db():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok"
    except SQLAlchemyError as error:
        return f"error: {type(error).__name__}"


def check_ollama():
    info = {
        "url": settings.OLLAMA_BASE_URL,
        "configured_model": settings.OLLAMA_MODEL or None,
        "models": [],
        "model_installed": False,
    }
    # Built directly instead of via get_provider(), so the status page still
    # works when OLLAMA_MODEL isn't set yet.
    provider = OllamaProvider(
        base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_MODEL
    )
    try:
        models = provider.list_models(timeout=3)
    except ProviderError as error:
        info["status"] = f"error: {type(error).__name__}"
        return info
    info.update(
        {
            "status": "ok",
            "models": models,
            "model_installed": bool(settings.OLLAMA_MODEL)
            and settings.OLLAMA_MODEL in models,
        }
    )
    return info


@app.get("/api/v1/status")
def status():
    """Shows whether the database and Ollama can be reached from this container."""
    return {"api": "ok", "db": check_db(), "ollama": check_ollama()}


@app.get("/api/v1/ollama/test")
def ollama_test(prompt: str = "Say hello."):
    """Sends one prompt to the model to prove Ollama is usable."""
    try:
        reply = get_provider().generate(prompt)
    except ProviderConfigError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "message": str(error),
                "url": settings.OLLAMA_BASE_URL,
                "model": settings.OLLAMA_MODEL,
                "ollama_status": error.status_code,
                "ollama_body": error.body,
            },
        )
    except ProviderError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return {"model": reply.model, "response": reply.text}
