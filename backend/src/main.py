"""
FastAPI application entry point.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Operon",
    description="AI-powered business operations platform",
    version="0.1.0",
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "operon"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Operon API"}
