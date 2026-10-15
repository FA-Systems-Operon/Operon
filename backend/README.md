# Operon Backend

FastAPI service backed by PostgreSQL (SQLAlchemy 2 + psycopg 3).

## Running locally

```bash
cp .env.example .env     # then set POSTGRES_PASSWORD (required)
docker compose up --build api db
```

The API is served on port 8000 (docs at `/api/v1/docs`). Postgres runs in the
`db` service (database `operon`, user `operon`, password from `POSTGRES_PASSWORD`).

## Database schema (no migrations yet)

Tables are created when the app starts, using `Base.metadata.create_all()` in
`src/main.py`. This only creates tables that don't exist yet. It never changes
existing ones.

So after changing a model in `src/models.py`, reset your local database:

```bash
docker compose down -v   # -v deletes the db_data and document_storage volumes
docker compose up --build api db
```

Alembic was removed on purpose for now. It should come back before we have any
data we can't wipe (shared staging, prod, or real client data).
