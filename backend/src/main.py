"""
FastAPI application main entry point.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle events."""
    logger.info("Operon backend starting...")
    yield
    logger.info("Operon backend shutting down...")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Operon",
        description="AI-powered business operations platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "operon"}

    # API documentation
    @app.get("/")
    async def root():
        return {"message": "Operon API", "docs": "/docs"}

    logger.info("FastAPI app created: Operon")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    import os
    # Only bind to all interfaces in production (via environment variable)
    # Development defaults to localhost for security
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", 8080))
    uvicorn.run(app, host=host, port=port)
