FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade --only-binary=:all: -r /code/requirements.txt

COPY --chown=appuser:appuser ./src /code/src

USER appuser

CMD ["fastapi", "run", "src/main.py", "--port", "8000"]
