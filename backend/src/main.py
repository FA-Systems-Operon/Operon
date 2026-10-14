import os

import httpx
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip(
    "/"
)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "").strip()

app = FastAPI(
    title="Operon API",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
print(
    f"Ollama URL: {OLLAMA_BASE_URL} | model: {OLLAMA_MODEL or '(OLLAMA_MODEL not set)'}",
    flush=True,
)


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
        "url": OLLAMA_BASE_URL,
        "configured_model": OLLAMA_MODEL or None,
        "models": [],
        "model_installed": False,
    }
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        response.raise_for_status()
        models = [model["name"] for model in response.json().get("models", [])]
        info.update(
            {
                "status": "ok",
                "models": models,
                "model_installed": bool(OLLAMA_MODEL) and OLLAMA_MODEL in models,
            }
        )
        return info
    except httpx.HTTPError as error:
        info["status"] = f"error: {type(error).__name__}"
        return info


@app.get("/api/v1/status")
def status():
    """Shows whether the database and Ollama can be reached from this container."""
    return {"api": "ok", "db": check_db(), "ollama": check_ollama()}


@app.get("/api/v1/ollama/test")
def ollama_test(prompt: str = "Say hello."):
    """Sends one prompt to the model to prove Ollama is usable."""
    if not OLLAMA_MODEL:
        raise HTTPException(
            status_code=503,
            detail="OLLAMA_MODEL is not set. Add it to your .env (see .env.example).",
        )
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Reached Ollama, but it rejected /api/generate",
                "url": OLLAMA_BASE_URL,
                "model": OLLAMA_MODEL,
                "ollama_status": error.response.status_code,
                "ollama_body": error.response.text,
            },
        )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach Ollama at {OLLAMA_BASE_URL}: {type(error).__name__}",
        )
    return {"model": OLLAMA_MODEL, "response": response.json()["response"]}
