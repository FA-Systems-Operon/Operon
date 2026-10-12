"""
FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

import src.models  # noqa: F401  (importing registers the tables on Base.metadata)
from src.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup: create any tables that don't exist yet.

    create_all never alters existing tables, so schema changes need a DB reset
    until Alembic is added back (see backend/README.md).
    """
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Operon",
    description="AI-powered business operations platform",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "operon"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Operon API"}
