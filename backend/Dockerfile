FROM python:3.13-slim

# Create the non-root user and the document storage dir it owns
# (a volume mounted at /code/storage inherits this ownership)
RUN useradd --create-home --uid 1000 appuser && \
    mkdir -p /code/storage && chown appuser:appuser /code/storage

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade --only-binary=:all: -r /code/requirements.txt

COPY --chown=appuser:appuser ./src /code/src

USER appuser

CMD ["fastapi", "run", "src/main.py", "--port", "8000"]
