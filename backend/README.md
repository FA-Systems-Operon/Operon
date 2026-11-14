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
| `GET /api/v1/client-profiles/{profile_id}/latest-approved` | Highest numbered approved version of this profile. |
| `GET /api/v1/playbooks/{playbook_id}/latest-approved` | Highest numbered approved version of this playbook. |

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


## Source-linked draft profiles (#40)

`POST /api/v1/client-profiles/{profile_id}/source-drafts` accepts the #39 output:
`name`, `needs`, `goals`, and `source_references` (each with `field`,
`document_id`, and `quote`). Create the profile first using the existing endpoint.
Documents must belong to that profile's client and have saved extracted text.
Missing profiles return 404; invalid or incomplete evidence returns 422 without
saving a version. Document IDs must be stored UUIDs. Quote matching verifies
provenance, not whether the model's interpretation is correct.

A successful request returns 201 with a new draft version. Profile values and
references are stored together in the existing immutable `data` JSON snapshot;
no migration is required, and old versions remain unchanged. Retrieve evidence
through `GET /api/v1/client-profiles/{profile_id}/versions` in each version's `data`.
The existing latest-approved endpoint continues to return only approved versions.
Like the other API routes, it lives under `/api/v1`, so the frontend reaches
it through the Vite dev proxy. Existing generic profile endpoints keep their current behavior.

## Onboarding draft job (#36)

Uploading a document only saves it. The onboarding agent needs both of a
client's sources, so a draft starts in a separate call once the transcript and
the intake answers are uploaded (the upload page makes it from `onUploaded`):

`POST /api/v1/clients/{client_id}/onboarding-jobs`

```json
{"transcript_document_id": "<uuid>", "intake_document_id": "<uuid>"}
```

Both documents must belong to the client (404 otherwise) and have the matching
`kind`, `transcript` and `intake` (422 otherwise). The call saves a `pending`
job pinned to those two documents and returns `201`. After the response is
sent, a FastAPI background task:

1. extracts both documents' text, reusing text that was already extracted,
2. sends exactly those two documents to the source-linked profile prompt (#39);
   other documents the client has are never included,
3. saves the validated result as a new draft version of the client's newest
   profile, creating a profile if the client has none (#40).

There is one job per transcript/intake pair. Calling again with the same pair
returns the existing job with `200` and starts nothing new; if that job had
failed, it is queued again. A new pair (for example a corrected transcript)
gets its own job.

The status moves `pending` → `running` → `succeeded` or `failed`, and each step
is committed so it can be watched while the model runs. Check it with
`GET /api/v1/clients/{client_id}/onboarding-jobs/{job_id}`: `status`, a short
`error` on failure, `result_version_id` on success, and timestamps. Another
client's job returns 404.

Failures are recorded on the job and never undo the uploads or their extracted
text. Model errors, unsupported evidence, malformed replies, or a document
without text save no profile version. The full traceback goes to the server
log; `error` stays short and does not include model output.

A job runs only when it is `pending`, so running the same job twice does
nothing. Crash recovery and retries are covered in the next section (#37).

New databases get the table from `create_all`. For an existing database, apply
`backend/migrations/004_add_onboarding_jobs.sql`.

## Job recovery and retries (#37)

The pending job is committed before anything runs, so a crash or restart can't
lose it. A single worker thread, started with the API, then:

- runs due `pending` jobs one at a time, oldest first, including jobs whose
  start call's background task never ran;
- every `JOB_POLL_SECONDS`, puts `running` jobs whose lease has expired back to
  `pending`, or marks them `failed` once they have no attempts left.

Claiming is recovery-safe. A runner claims a job with a conditional update that
counts the attempt (`attempts`) and starts a lease of `JOB_TIMEOUT_SECONDS`.
The worker skips rows another runner has locked (`SKIP LOCKED`). A run can only
finish the attempt it claimed, in the same transaction that saves the draft, so
a run that outlived its lease can't save a second draft.

Temporary failures (model unreachable, timed out or answering with an error,
storage unavailable) go back to `pending` with `error` and `next_attempt_at`
set, waiting `JOB_RETRY_DELAY_SECONDS` times the attempt number. Bad model
output, unsupported evidence, a missing file or a missing model setting fail
straight away, because retrying wouldn't help.

| Setting | Default | Meaning |
| --- | --- | --- |
| `BACKGROUND_WORKER_ENABLED` | `true` | Start the worker with the API. |
| `JOB_POLL_SECONDS` | `5` | Wait between worker rounds. |
| `JOB_TIMEOUT_SECONDS` | `600` | Lease length; a longer run counts as abandoned. Keep it above `OLLAMA_TIMEOUT_SECONDS`. |
| `JOB_RETRY_ATTEMPTS` | `3` | Retries after the first attempt. |
| `JOB_RETRY_DELAY_SECONDS` | `30` | Base wait before a retry. |

The worker assumes one API process. `MAX_CONCURRENT_JOBS` in
`compose.prod.yaml` is not used yet. After a crash, a job that was running is
retried once its lease expires, so up to `JOB_TIMEOUT_SECONDS` later.
The status endpoint also returns `attempts` and `next_attempt_at`. Starting a
failed pair again resets its attempts.

For an existing database, apply `backend/migrations/005_add_onboarding_job_retries.sql`
after 004.


## Missing onboarding information and potential conflicts (#43)

Source-linked drafts now extract these nullable, source-backed text fields:
`business_number`, `website`, `domain_platform`, `meta_business_manager`,
`facebook_page`, `instagram`, `phone_number`, `email`, and `business_address`.
These nine fields are mandatory for completeness checks. Existing `name`, `needs`,
and `goals` remain supported but are not mandatory. No restrictive business-number,
URL, or domain-platform format rules are assumed. Account values are IDs, URLs, or
handles, never passwords. Either source may supply a field.

The generation prompt uses a compact JSON output contract, compares both sources
before selecting values, and keeps list values separate from their evidence.
The provider receives the Pydantic JSON schema to constrain decoding, including
this job's document IDs. Strict validation still applies to every response.
Ordinary text/JSON provider calls retain their existing behavior.

During generation only, missing scalar references may be completed from exact
literal value occurrences in the supplied sources. An added terminal period/question/exclamation mark may be removed only when
the remaining quote occurs exactly in the same document. Unsupported text and
changes inside a quote are never matched approximately. References redundantly repeated for a null
conflicted scalar are removed only when they exactly duplicate already validated
conflict alternatives; both claims remain preserved there. Paraphrased values
still require model-supplied evidence. The direct source-draft API remains strict
and does not apply this generation normalization.

The generation prompt proposes `conflicts`, each with `field`, `explanation`, and
exactly two `alternatives` containing `value`, `document_id`, and an exact `quote`.
One alternative must cite a stored transcript and the other a stored intake for
this client. Both claims concern the same fact/context; complementary information
and formatting differences are not inherently conflicts. Scalar fields with a
conflict stay null, with both alternatives available for review. Group-level
`needs`/`goals` conflicts and existing item paths are also supported. Evidence
validates provenance, not the model's semantic interpretation.

The server recomputes `assessment: {rules_version: 1, missing_fields: [...]}`
during generation and source-draft saving. A mandatory field is missing when it
has neither a supported scalar value nor a validated conflict. Incoming assessment
claims cannot suppress missing fields. Unknown paths, duplicate conflicts, blank
values, invented quotes, wrong kinds or another client's evidence are rejected.
A failed save produces no new version; job validation failures follow existing
failure handling. Old ordinary source references can still use untyped documents,
but conflict evidence requires stored kinds.

Everything is saved in the existing immutable version JSON; no migration is
needed. Historical versions without assessment stay unassessed. The generic
profile update endpoint remains an unvalidated JSON editing endpoint and does not
recompute completeness or establish conflict-resolution/approval guarantees.
The review edit endpoint (#60) invalidates assessment after edits (see below).
The source-draft endpoint validates the supplied evidence; it does not scan
all documents a client owns. The onboarding job compares its exact pinned pair.

Resolution and approval blocking are follow-up review-flow work, as described in
the architecture; this change does not implement those controls. The agent makes at most one additional model call when structured output or
evidence validation fails, following the architecture's bounded repair rule.
The original documents, failed reply and validation error are supplied as data;
the repaired response must pass the same full validator. A second invalid reply
fails the job with no draft saved. Provider failures still use the existing job
retry policy; they do not trigger this validation repair.


## Review inbox (#54)

`GET /api/v1/reviews` lists the profile drafts waiting for a reviewer, newest
first (by `created_at`, then `version_id`). No drafts returns `200` with `[]`.

```json
[
  {
    "version_id": "<uuid>",
    "client_profile_id": "<uuid>",
    "version_number": 2,
    "client_id": "<uuid>",
    "client_name": "Maya's Bakery",
    "created_at": "2026-11-09T14:03:12.511Z",
    "status": "draft"
  }
]
```

A version is listed when all of these hold:

- it is the highest `version_number` of its profile; an older draft with a
  newer version (approved or not) is superseded and not listed,
- its status is `draft` or `in_review` (nothing sets `in_review` yet),
- its `data` is not empty. This leaves out the `{}` version 1 that
  `POST /client-profiles` creates. Drafts from the onboarding job, the
  source-draft endpoint and `PUT` corrections always have data, so a correction
  to a generated draft replaces it in the inbox.

There is one item per profile, not per client: a client with two profiles that
both have a pending draft appears twice. `created_at` is when that version was
saved, which for a generated draft is when it was generated. `version_id` and
`client_profile_id` are what the draft detail view (#57) needs to open it.

The list is not paginated; it only holds unreviewed drafts. If it grows,
cursor paging on `(created_at, version_id)` fits the existing order.

## Review draft detail (#57)

`GET /api/v1/reviews/profiles/{profile_id}/versions/{version_id}` returns what
the review page needs to open one draft, in a single call:

```json
{
  "version": { "id": "<uuid>", "client_profile_id": "<uuid>", "version_number": 2,
               "status": "draft", "data": { "...": "the saved draft" },
               "created_at": "...", "approved_by": null, "approved_at": null },
  "client": { "id": "<uuid>", "name": "Maya's Bakery", "created_at": "..." },
  "documents": [ { "id": "<uuid>", "original_filename": "call.txt",
                   "kind": "transcript", "...": "same fields as the documents list" } ]
}
```

`version` has the same shape as the profile versions list. `documents` are the
client's source documents (oldest first, no storage key), so the page can show
which file and kind each quote's `document_id` refers to. Any version can be
opened, not only drafts awaiting review. The version is looked up within the
profile: a version of another profile, or an unknown profile or version,
returns `404`. The route is under `/api/v1` already and does not depend on the
profile routes moving there.

## Save reviewer edits (#60)

`POST /api/v1/reviews/profiles/{profile_id}/versions/{version_id}/edits`
accepts only a `changes` map, for example:

```json
{"changes": {"name": "Corrected name", "email": null, "needs/0": "More bookings"}}
```

The version in the URL is the loaded base. A transaction locks the profile and
checks that this is still its latest version, in `draft` or `in_review` with no
approval timestamp. A superseded or decided base returns `409`; a missing or
mismatched profile/version returns `404`. Unknown fields, non-text values,
new/noncanonical list indexes, blank/null list items, and a non-object stored base
return `422`. Scalars
are trimmed and may be cleared to null; no extra email/URL/phone formats are imposed.

The server copies the stored base, applies only permitted corrections, and inserts
an immutable, unapproved version preserving the base's `draft` or `in_review`
status, using the existing version numbering and unique constraint. Success returns
the saved version (`201`). Empty or unchanged changes
still check freshness and return the current base (`200`), without another version;
this supports retry after reverting local changes. Failure rolls back the save.
The generic profile PUT now takes the same parent lock (its JSON contract is unchanged).
Source-draft generation and profile approval already take that lock.

Changed snapshots use the existing nullable `assessment` format: `null` means
unassessed. Original references and conflict alternatives remain unchanged as
historical evidence. They do not verify reviewer corrections, and editing a
conflicted scalar does not resolve the conflict. The source-generation validator
is unchanged. Prior versions remain intact; no migration is needed. Saving does
not approve anything, change the latest-approved profile, or mark artifacts stale.

The review page offers explicit Save, retains local edits on errors, and adopts
the response's version and URL on success, notifying the hash router immediately.
Pending input and an in-flight request
disable Save; a known stale response also disables it and directs the reviewer to
the latest draft in the inbox. Failed requests require a successful retry before
the local save gate clears, even if the edits are reverted.

`draftSaveGate` supplies the save prerequisite for #62: block approval for unsaved
edits, pending input, saving, save failure, known staleness, or noneditable status.
It is not an authorization or conflict-resolution decision. There is no Approve
button or approval-endpoint change in #60. **Approval-time freshness, permissions,
and conflict/field decisions remain #62 and the wider review workflow.** No
navigation guard, autosave or browser storage is added; leaving before a successful
save discards local edits. #66's full acceptance verification remains separate.

## Reject a draft (#63)

`POST /api/v1/reviews/profiles/{profile_id}/versions/{version_id}/reject`
takes a required reason:

```json
{"reason": "Intake belongs to a different client"}
```

The reason is trimmed and must be 1–500 characters (`422` otherwise; unknown keys
are also `422`). The same freshness check as saving edits applies: the version
must be the profile's latest, in `draft` or `in_review`, and unapproved, or the
request returns `409`; a missing or mismatched profile/version returns `404`.

Rejecting updates that version in place: `status` becomes `rejected`, and
`rejection_reason` and `rejected_at` are stored. No new version is created and no
approval fields are set, so the latest-approved profile and artifact staleness are
unchanged. Once set, the reason and time cannot be changed (immutability guard).
Rejected drafts leave the review inbox, and approving a rejected version returns
`409`. Since #62 the signed-in reviewer is stored as `rejected_by`.

The review page shows a Reject button beside Save. It opens a reason form, blocks
an empty reason, warns that unsaved edits will be discarded, and on success shows
the draft as rejected with its reason. Dedicated rejection tests are #64.

For an existing database, apply
`backend/migrations/006_add_profile_version_rejection.sql` after 005.

## Approve a draft (#62)

`POST /api/v1/reviews/profiles/{profile_id}/versions/{version_id}/approve` (no
body) saves the loaded draft, including any saved reviewer edits, as a **new**
version with `status: approved`, `approved_by` (the signed-in user) and
`approved_at`. It returns `201` with `{"version": ..., "newly_stale_artifact_version_ids": [...]}`.
The draft row itself is not rewritten. Artifacts built from older profile versions
are marked stale in the same transaction.

The version must still be the profile's latest, in `draft` or `in_review`, and
unapproved; otherwise `409`. A repeated submit or a second reviewer approving at
the same time therefore gets `409` instead of a second approved copy (the profile
row lock serialises them). A page that missed a newer save, approval or rejection
also gets `409`. An empty version (the `{}` placeholder) is `422`; a missing or
mismatched profile/version is `404`.

**Permissions.** Edit, reject and approve now need a signed-in `reviewer` or
`admin` and the `X-CSRF-Token` header: `401` when signed out, `403` for a viewer
or a missing/wrong CSRF token. The frontend sends the session cookie and token on
these calls and hides the review controls from viewers. Reading drafts and the
inbox is unchanged.

The review page's Approve button sits next to Save. It is disabled until edits are
saved with nothing pending (`draftSaveGate`) and while a request is in flight; on
success the page opens the new approved version.

Not changed: the older `POST /api/v1/client-profiles/{id}/versions/{vid}/approve`
(approver in the body, approves in place) is still there and unauthenticated; the
staleness and versioning tests use it. Unresolved source conflicts do not block
approval; the reviewer decides by editing the field before approving.

For an existing database, apply
`backend/migrations/007_add_profile_version_rejected_by.sql` after 006.
