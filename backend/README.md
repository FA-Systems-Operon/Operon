# Operon Backend

FastAPI service backed by PostgreSQL (SQLAlchemy 2 + psycopg 3).

## Running locally

```bash
docker compose up --build backend postgres
```

The API is served on port 8080 and Postgres on `localhost:5432`
(database `operon_dev`, user `operon_user`, password from `POSTGRES_PASSWORD` in `.env`,
default `operon_dev_password`).

## Database schema (no migrations yet)

Tables are created when the app starts, using `Base.metadata.create_all()` in
`src/main.py`. This only creates tables that don't exist yet. It never changes
existing ones.

So after changing a model in `src/models.py`, reset your local database:

```bash
docker compose down -v   # -v deletes the postgres_data and document_storage volumes
docker compose up --build backend postgres
```

Alembic was removed on purpose for now. It should come back before we have any
data we can't wipe (shared staging, prod, or real client data).
