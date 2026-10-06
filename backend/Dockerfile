# Builder stage: install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (for layer caching)
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Runtime stage: minimal final image
FROM python:3.11-slim

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy only necessary application files (not entire directory)
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser alembic.ini .

# Set PATH to use venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run migrations and start application
CMD ["/bin/bash", "-c", "alembic upgrade head && uvicorn src.main:app --host 127.0.0.1 --port 8080"]
