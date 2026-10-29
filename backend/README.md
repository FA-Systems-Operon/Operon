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

## Document kind and client list (#35)

Uploads accept an optional `kind` form field, `transcript` or `intake`, so the
agent and reviewers can tell a sales transcript from intake answers. It is
returned on every document response and is `null` for documents uploaded
without one. Any other value returns `422` and nothing is saved.

`GET /api/v1/clients` lists every client sorted by name, for the upload screen's
client picker. The client endpoints moved from `/clients` to `/api/v1/clients`,
matching the documents endpoints, so the frontend proxy and Caddy forward them.

Fresh databases get the `kind` column through `create_all`. An existing
development database needs this additive script, which can be rerun and leaves
existing documents unchanged with `kind = NULL`:

```bash
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < backend/migrations/003_add_document_kind.sql
```

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

## Latest approved profile and playbook versions (#19)

This backend feature builds on `feature/18-version-logic` plus current `main`.
Each version has a nullable, timezone-aware `approved_at` timestamp. `NULL` means
unapproved. Creation and editing always produce unapproved versions; approval is
not inherited from the previous snapshot. Approval metadata is separate from the
immutable snapshot data.

| Request | Result |
| --- | --- |
| `GET /client-profiles/{profile_id}/latest-approved` | Highest numbered approved version of this profile. |
| `GET /playbooks/{playbook_id}/latest-approved` | Highest numbered approved version of this playbook. |

Both endpoints return `200` with the version ID, parent ID, `version_number`,
`data`, `created_at`, and `approved_at`. Ordering uses **version number**, not
approval time: approving version 2 after version 3 still returns version 3.
A newer draft is excluded. UUID remains a deterministic final tie-breaker in
the query, but the current schema rejects duplicate version numbers per parent.

An existing record with no approved versions returns `404` with
`{"detail": "No approved version found"}`. An unknown parent returns `404` with
`Client profile not found` or `Playbook not found`. Invalid UUIDs return `422`.
The service functions in `src/versioning.py` return `None` when no approved
version matches, including for an unknown parent.

#19 introduced retrieval only. The #20 branch now adds approval endpoints that
set `approved_at` and mark dependent artifacts stale in the same transaction.
Sending an `approved_at` key in an update endpoint's JSON data does not approve a
version. No frontend approval controls are included. The current approval endpoints
accept `approved_by` in the request; authenticated reviewer authorization and
audit tracking remain separate work.

### Existing development databases

Fresh databases get the new columns through `create_all`. If you already ran
#18's version tables, apply this additive script before starting the updated API:

```bash
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < backend/migrations/001_add_version_approved_at.sql
```

The script can be rerun. It preserves existing data and leaves all existing
versions unapproved. Do not infer approval from their age or version number.

### Tests

With the backend and test requirements installed and `TEST_DATABASE_URL` pointing
to a dedicated database whose name ends in `_test`:

```bash
pytest tests/test_latest_approved.py -q
```

The existing CI `pytest --cov` command includes these tests automatically. Tests
use PostgreSQL and create approval timestamps directly; they do not require an
approval UI, Ollama, or a running frontend.

## Upgrade existing version tables for staleness (#20/#21)

The staleness branch adds `status` and `approved_by` to profile/playbook versions,
plus unique `(parent_id, version_number)` constraints. `create_all` does not alter
existing tables. To preserve an existing #18/#19 development database, stop the API
and apply the additive upgrade before starting the new code:

```bash
docker compose stop api
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < backend/migrations/002_version_review_and_uniqueness.sql
docker compose up --build -d api
```

Run this only when both profile/playbook version tables already exist. Fresh
databases receive the current schema at startup, including new artifact tables.
The script adds `approved_at` too if the earlier upgrade was not applied.

When adding `status`, only existing non-null approval timestamps are mapped to
`approved`; other records become `draft`. Unknown historical reviewers stay NULL.
Rerunning the script preserves existing statuses and approval metadata. It adds
constraints for **both** profile and playbook version numbers. If duplicates exist,
the whole transaction aborts without deleting or renumbering any history. Inspect
and resolve those records explicitly before rerunning; do not discard history to
make the constraint pass.

Tests for preservation, reruns, and rollback on duplicates are in
`tests/test_version_review_migration.py`. #21's requirement-to-test mapping and
CI command are in `tests/README.md`.
