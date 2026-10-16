FROM python:3.13-slim

# Create the non-root user and the document storage dir it owns
# (a volume mounted at /code/storage inherits this ownership)
RUN useradd --create-home --uid 1000 appuser && \
    mkdir -p /code/storage && chown appuser:appuser /code/storage

WORKDIR /code

# Hashed lock file generated from requirements.txt (see README.md)
COPY ./requirements.lock /code/requirements.lock

RUN pip install --no-cache-dir --upgrade --require-hashes --only-binary=:all: \
    -r /code/requirements.lock

COPY --chown=appuser:appuser ./src /code/src

USER appuser

CMD ["fastapi", "run", "src/main.py", "--port", "8000"]
