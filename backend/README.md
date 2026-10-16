# Operon Backend

FastAPI service backed by PostgreSQL (SQLAlchemy 2 + psycopg 3).

## Running locally

```bash
cp .env.example .env     # then set POSTGRES_PASSWORD (required)
docker compose up --build api db
```

The API is served on port 8000 (docs at `/api/v1/docs`). Postgres runs in the
`db` service (database `operon`, user `operon`, password from `POSTGRES_PASSWORD`).

## Dependencies (hashed lock files)

`requirements.txt` (app) and `requirements-dev.txt` (tests) list the direct
dependencies. Installs use generated lock files that pin every package,
including transitive ones, with SHA-256 hashes:

- `requirements.lock`: installed by the Docker image.
- `requirements-dev.lock`: app + test dependencies, installed by CI.

Don't edit the `.lock` files by hand. **Rerun both commands whenever
`requirements.txt` or `requirements-dev.txt` changes**, and commit the updated
lock files with that change. Run them from the repo root (not `backend/`) with
[uv](https://docs.astral.sh/uv/):

```bash
uv pip compile backend/requirements.txt \
  --universal --python-version 3.13 --generate-hashes \
  --exclude-newer "14 days" --exclude-newer-package pypdf=false \
  -o backend/requirements.lock

uv pip compile backend/requirements.txt backend/requirements-dev.txt \
  --universal --python-version 3.13 --generate-hashes \
  --exclude-newer "14 days" --exclude-newer-package pypdf=false \
  -o backend/requirements-dev.lock
```

The locks target Python 3.13. `--universal` makes them work on both Linux x86
(CI) and ARM (Docker on Macs). `--exclude-newer "14 days"` keeps transitive
dependencies on releases at least two weeks old. `--exclude-newer-package`
exempts `pypdf` because its pin in `requirements.txt` is newer than that. Remove
the exemption once that pin is two weeks old.

To run the tests locally, install the dev lock into a virtualenv:

```bash
pip install --require-hashes --only-binary=:all: -r backend/requirements-dev.lock
```

## Database schema (no migrations yet)

Tables are created when the app starts, using `Base.metadata.create_all()` in
`src/main.py`. This only creates tables that don't exist yet. It never changes
existing ones.

Adding a new table only requires rebuilding and restarting the backend. Startup
creates missing tables without changing existing ones or deleting uploaded files.

After changing columns or constraints on an existing table in `src/models.py`,
reset your local development database:

```bash
docker compose down -v   # -v deletes the db_data and document_storage volumes
docker compose up --build api db
```

Alembic was removed on purpose for now. It should come back before we have any
data we can't wipe (shared staging, prod, or real client data).

## Extracted document text

The `extracted_texts` table stores derived plain text separately from the original
uploaded file. Its primary key, `document_id`, also references `source_documents`,
so each document has at most one extracted-text record. The record contains a
PostgreSQL `TEXT` value and a database-generated, timezone-aware `extracted_at`.

A document can exist before extraction. Deleting its extracted-text record keeps
the source document; deleting the source document removes its derived text.

## Document extraction API

Uploads are validated before any file or metadata is saved: unsupported formats
return `415`, and corrupt or unreadable content returns `422`. Empty files still
return `400`, and oversized files return `413`. Validation reuses the extractors
but does not save extracted text; request extraction separately to persist it.
Previously stored files retain extraction-time error handling.

Upload the original file first, then request extraction separately. TXT, Markdown
(`.md`/`.markdown`), and unencrypted text-based PDF are supported. OCR and audio
transcription are outside this feature. TXT and Markdown support UTF-8 and
BOM-marked UTF-16.

PDFs are limited to 100 pages, including blank and image-only pages. Larger PDFs
return `422` before any text is extracted, during both upload validation and
extraction of previously stored files.

| Request | Behavior |
| --- | --- |
| `POST /api/v1/clients/{client_id}/documents` | Saves the original file and returns its metadata (`201`). |
| `POST /api/v1/clients/{client_id}/documents/{document_id}/extract` | Extracts and saves text, or returns the existing result (`200`). No request body is needed. |
| `GET /api/v1/clients/{client_id}/documents/{document_id}/text` | Returns saved text (`200`); does not perform extraction. |

The extraction and text responses contain `document_id`, `text`, and
`extracted_at`. Repeated extraction keeps the saved result and timestamp. The
original upload and metadata stay unchanged. A filename's extension selects the
extractor; files without extensions use their recorded MIME type.

After an extractor fix, use
`POST /api/v1/clients/{client_id}/documents/{document_id}/extract?force=true`
to re-extract the original with the current extractor. This replaces the saved
text and refreshes `extracted_at`, even if the text is unchanged. The document
lock still serializes extraction requests. If re-extraction fails, the previous
text and timestamp remain available. Normal requests continue to reuse saved
text; extractor updates do not automatically refresh existing results. The
100-page PDF limit also applies to forced extraction.

Both text endpoints return `404` for another client's document or an unknown ID.
Text retrieval also returns `404` before successful extraction. Extraction returns
`415` for unsupported formats, `422` for invalid or unreadable content (including
encrypted/no-text PDFs), `409` if the original file is missing, and `503` for other
storage access failures.

### Try the complete flow

Rebuild the backend so it loads the new routes and creates any missing tables:

```bash
docker compose up --build -d api db
```

For a local demonstration, create a synthetic client:

```bash
docker compose exec -T db psql -U operon -d operon \
  -c "INSERT INTO clients (id, name) VALUES \
  ('11111111-1111-1111-1111-111111111111', 'Demo Client') \
  ON CONFLICT (id) DO NOTHING;"
```

Upload a sample Markdown transcript:

```bash
printf '%s\n' '# Client meeting' '' '**Alice:** Hello.' > /tmp/operon-transcript.md
curl -X POST http://localhost:8000/api/v1/clients/11111111-1111-1111-1111-111111111111/documents \
  -F 'file=@/tmp/operon-transcript.md;type=text/markdown'
```

Copy the returned `id` and replace `DOCUMENT_ID` in both requests:

```bash
curl -X POST http://localhost:8000/api/v1/clients/11111111-1111-1111-1111-111111111111/documents/DOCUMENT_ID/extract
curl http://localhost:8000/api/v1/clients/11111111-1111-1111-1111-111111111111/documents/DOCUMENT_ID/text
```

Both responses should contain `Client meeting\n\nAlice: Hello.` as their `text`.
The same routes are available interactively at `http://localhost:8000/api/v1/docs`.
