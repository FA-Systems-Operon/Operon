# Shared test data

All data is synthetic. Fixtures are function-scoped; database rows use the
existing isolated `*_test` database and file storage uses `tmp_path`.

- `demo_client`: one persisted client, unchanged for existing tests.
- `client_factory(name="Demo Client")`: create additional independent clients.
- `stored_document(data=..., filename=..., content_type=...)`: create a document
  for `demo_client` and save its bytes in temporary storage. Returns the model.
  Pass `owner=client_factory("Other Client")` to create one for another client;
  both the database association and storage key use that client.
  This deliberately bypasses upload validation for service and legacy-file tests.
- `sample_profile`: a fresh dictionary with business name, industry, and goals.
  It is illustrative data only, not a persisted profile version.
- `tests.sample_data.make_pdf(pages, password=None)`: generate real PDF bytes,
  including blank or encrypted samples. TXT and Markdown samples can be passed
  as bytes to `stored_document`.
- `tests.sample_data.invalid_upload_samples()`: reusable unsupported, invalid
  UTF-8, blank, malformed, and encrypted upload cases with expected statuses.

Existing extraction, upload-rejection, and client-isolation tests exercise these
helpers. Run the suite from the repository root with `pytest`.


## Ingestion regression tests (#55)

Run `python -m pytest tests/test_documents.py -q` for upload, storage integrity,
client association/isolation, retrieval, and rejection checks. Supported TXT,
Markdown, and PDF uploads must retain their original bytes and metadata.
Rejected uploads must provide a clear error, leave no new record or file, and
preserve existing documents, including when an invalid upload reuses a filename.

The existing `.github/workflows/build.yml` runs these tests as part of the full
`pytest --cov --cov-branch --cov-report=xml` suite on PR creation and updates,
using a disposable PostgreSQL service. No separate CI job is needed.

## Versioning regression tests (#21)

The implementation branch is based on `feature/20-Staleness` at `d05ddf2`,
which already includes #19 and the initial staleness tests. Reuse those tests;
this suite adds complete workflow and regression coverage rather than duplicating
all the existing assertions.

| Requirement | Coverage |
| --- | --- |
| Editing approved profiles/playbooks creates a new draft and preserves history | `test_versioning_workflow.py`, `test_latest_approved.py`, `test_version_immutability.py` |
| Approving a newer source marks dependent artifacts stale | `test_versioning_workflow.py`, `test_staleness.py` |
| Latest-approved retrieval never returns a draft | `test_latest_approved.py`, profile/playbook endpoint tests |
| Failed staleness marking rolls back approval | `test_versioning_workflow.py` |
| Test database configuration precedes model imports | `test_test_database_setup.py` (fresh Python subprocess, no DB connection) |
| Existing databases upgrade without losing history | `test_version_review_migration.py` (isolated temporary schemas) |
| Duplicate version numbers are rejected | `test_version_immutability.py`, `test_versioning_workflow.py`, migration tests |

**Meaning of stale:** saving an unapproved correction does not supersede the
current approved source. Approving a higher numbered source version marks its
dependent **artifacts** stale. The older source remains approved history; its
content and approval timestamp do not change. Approving an older version later
does not roll back the current approved source.

Install the backend's locked test dependencies (see `backend/README.md`), set
`TEST_DATABASE_URL` to a dedicated PostgreSQL database ending in `_test`, then run:

```bash
python -m pytest tests/test_versioning_workflow.py tests/test_latest_approved.py \
  tests/test_staleness.py tests/test_version_immutability.py \
  tests/test_test_database_setup.py tests/test_version_review_migration.py -q
# Full CI command, also includes schema and endpoint tests:
python -m pytest --cov --cov-branch --cov-report=xml
```

No `DATABASE_URL` override is needed for tests. The test configuration validates
`TEST_DATABASE_URL` and sets `DATABASE_URL` before importing the models. The
fixture recreates ORM tables in that dedicated test database; never use a database
containing data you need to keep. Migration tests use separate temporary schemas.

The existing Build workflow runs the full suite against PostgreSQL on pull
requests. These test files are automatically included; no extra CI job is needed.
CI installation and collection failures must remain failures, not skipped tests.

Most versioning tests exercise PostgreSQL or HTTP endpoints and are integration
regression tests despite the issue's "unit tests" title. Schema validation tests
are unit tests. Approval identity is supplied by the test API helper; authenticated
reviewer authorization is separate from this issue.

## Source-linked draft acceptance (AT 3.2, #48)

Criterion: given a generated draft profile, when a reviewer opens it, every field
shows a link to the part of the transcript or intake form it came from. The model
is faked, so CI needs no Ollama. Controlled examples: `transcript_1.txt` with a
short intake form, plus an unnamed transcript-only call.

| Criterion part | Evidence |
| --- | --- |
| A generated draft is saved and read back with its references | `test_source_profile_acceptance.py::test_every_saved_field_links_to_its_source_passage` |
| Every populated field (name, each need, each goal) has a reference | same test (populated fields must equal the answer key) |
| Each reference is one of the client's stored documents, and its quote occurs in that document's text | same test (checked against the database) |
| Each reference points to the right document (intake-only facts cite the intake) | same test (quote occurs in no other document; kinds match the answer key) |
| A real quote cited from the wrong document is rejected (422) and not saved | `test_source_profile_acceptance.py::test_real_quote_cited_from_the_wrong_document_is_not_saved` |
| The reviewer sees one link per field to the correct document and quote | `frontend/src/components/DraftSourceView.acceptance.test.tsx` |

Invented quotes, unknown or other clients' documents and missing references are
already covered by `test_profile_sources_api.py` (#40) and `test_source_prompt.py` (#39).

```bash
python -m pytest tests/test_source_profile_acceptance.py tests/test_source_prompt.py \
  tests/test_profile_sources.py tests/test_profile_sources_api.py -q
cd frontend && npm test
```

**Limitation:** "when a reviewer opens it" is verified at component level with
`DraftSourceView`, since the review page (#57) is not built yet. The frontend
example copies the backend's saved data, so update both if the example changes.
Exact quote matching proves provenance, not that the passage supports the value;
that stays a reviewer judgement.
