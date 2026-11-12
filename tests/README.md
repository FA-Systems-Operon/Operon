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

## Missing/conflicting onboarding information (AT 3.3, #49)

The nine mandatory fields are business number, website, domain platform, Meta
Business Manager account, Facebook Page, Instagram, phone number, email, and
business address. Name, needs, and goals remain optional for completeness.
Either document can supply a field; conflicting scalar fields retain both
alternatives and a null value instead of silently choosing a winner.

| Requirement | Evidence |
| --- | --- |
| Server computes missing fields and validates every populated field's references | `test_profile_flags.py` |
| Both conflict values have exact quotes in this client's transcript/intake | `test_profile_flags.py` |
| Wrong client, unknown paths, wrong kinds, duplicate or fabricated evidence cannot save a draft | `test_profile_flags.py`, existing source validation tests |
| Generation through the pinned onboarding job saves flags and returns them through version retrieval | `test_profile_flags_acceptance.py` |
| Failed conflict validation saves no draft; approved history is preserved | same acceptance suite and #43 tests |
| Missing fields and both conflict claims appear beside their fields with correct source links | `frontend/src/components/DraftFlags.acceptance.test.tsx` |
| Legacy/unknown assessment handling, escaped text, group/item warnings, keyboard navigation | `frontend/src/components/DraftFlags.test.tsx` |

The five synthetic cases in `tests/fixtures/onboarding_flags/cases.json` are shared
by backend and frontend tests: a clear conflict, missing information, matching
values, complementary goals, and an uncertain potential disagreement. The reply
is controlled and the expected field lists are written in the fixture. The
backend replaces symbolic source names with stored document UUIDs; the component
checks source navigation through the host callback.

```bash
python -m pytest tests/test_profile_flags.py tests/test_profile_flags_acceptance.py -q
cd frontend
npm test
npm run build
```

The default suite uses a fake provider for deterministic validation and
integration checks. Three opt-in tests run the actual local provider through
uploads, job execution, persistence, and API retrieval. The UI is tested at component level: the full review
page and source-navigation implementation remain #57. The existing production
App does not yet display this component.

For real-model evaluation, start/configure the project's Ollama provider and run
from the repository root with the backend dependencies installed:

```bash
OLLAMA_MODEL=qwen2.5:14b PYTHONPATH=backend .venv/bin/python \
  scripts/evaluate_profile_flags.py > /tmp/operon-flags-evaluation.json
```

Set `OLLAMA_BASE_URL` if the endpoint differs from `http://localhost:11434`.
The command does not automatically load `.env`. The report records the model,
provider, source UUIDs, initial and repair prompt hashes, schema hash, model-call
count, duration, validated synthetic draft, missing/extra flags, and expected
alternatives. The evaluator uses the production generation/repair path. A nonzero exit signals unavailable provider,
invalid output or an answer-key mismatch. Manually inspect interpretation and
quotes as well; these eight cases are a regression sample, not a general accuracy
threshold or sponsor sign-off. See `docs/evaluation/us-3.3-status.md` for the
current evaluation status.


The additional cases in `tests/fixtures/onboarding_flags/additional_cases.json`
cover a phone conflict in prose, equivalent phone formatting, and completeness
when all facts come from one source. They were used during development and are
regression cases, not an independent held-out accuracy study. The evaluator runs
both fixed case files; it does not accept arbitrary source files.

To run the three live job/database checks against an isolated test database:

```bash
OLLAMA_MODEL=qwen2.5:14b OLLAMA_BASE_URL=http://127.0.0.1:11434 \
OLLAMA_TIMEOUT_SECONDS=180 RUN_OLLAMA_TESTS=1 \
TEST_DATABASE_URL='<dedicated PostgreSQL URL ending in _test>' \
  .venv/bin/python -m pytest tests/test_profile_flags_acceptance.py -k real_provider -q
```

As with the existing baseline live-model test, these opt-in functions are
excluded from CI coverage because CI has no Ollama service. They are run
separately and their results are documented in the evaluation status.

## Review inbox and draft detail (AT 4.1, #65)

Criteria: (1) given a draft awaiting review, when a reviewer opens the review
inbox, it is listed with the client name and generation time; (2) given a
reviewer selects it, the detail view shows the evidence and the proposed
profile fields side by side. Drafts are generated the way the app makes them:
both files are uploaded through the API, then the onboarding job drafts them with
a faked model, so CI needs no Ollama.

| Criterion | Evidence |
| --- | --- |
| (1) The awaiting draft is listed with its client name and the time the job saved it; an approved draft and the empty placeholder are not | `test_review_inbox_acceptance.py::test_inbox_lists_the_awaiting_draft_with_client_name_and_time` |
| (1) The inbox row shows the client name and the formatted generation time | `frontend/src/pages/ReviewInbox.acceptance.test.tsx` (criterion 1) |
| (2) Opening the item with the IDs the inbox returned gives the proposed fields, and every quote cites a returned document and occurs in the uploaded file of that kind | `test_review_inbox_acceptance.py::test_selected_draft_opens_with_its_fields_and_evidence` |
| (2) Clicking the row opens the detail page: field list and evidence panel in the same two-column body; choosing a field shows its quote and source document | `ReviewInbox.acceptance.test.tsx` (criterion 2) |
| The frontend's API replies have the real response shape | `test_review_inbox_acceptance.py::test_frontend_fixture_has_the_real_response_shape` against `fixtures/review_inbox/responses.json` |
| Empty state: no drafts gives `[]` and the inbox says so | `test_inbox_is_empty_when_no_draft_awaits_review`; `ReviewInbox.acceptance.test.tsx` (empty) |
| Error state: the inbox says it couldn't load, and Try again loads it | `ReviewInbox.acceptance.test.tsx` (error) |

Detailed filtering, ordering and 404 cases are in `test_reviews.py`, and the page
states in `ReviewInboxPage.test.tsx` and `ReviewDraftPage.test.tsx`.

```bash
python -m pytest tests/test_review_inbox_acceptance.py tests/test_reviews.py -q
cd frontend && npm test && npm run build
```

The frontend test was checked to fail when the inbox shows the wrong client
name or time, links to the wrong draft, drops a field, shows no quotes, loses its
empty message, or Try again does nothing. The backend test has not run locally
yet (Postgres was down); once it is up, confirm it fails when `reviews.py`
returns the client's `created_at` as the generation time, drops the
`data != {}` filter, or returns another client's documents, then revert.

**Limitations:** there is no authentication yet, so "a reviewer" is anyone who
opens the page. "Side by side" is checked in the markup (both columns inside
the two-column body), not visually; the CSS stacks them under 720px.

## Inline field editing (#59; reuse for AT 4.2, #66)

Task #59 covers local editing on the production review detail page only. Editable
statuses are `draft` and `in_review`; historical statuses remain read-only. The
name and nine onboarding fields accept nullable text. Boundary whitespace is
trimmed; clearing a scalar produces null. Existing needs/goals items accept
nonblank text, keeping their saved indexes. No list additions, deletions or
reordering are supported. Empty lists stay empty. No format validation is imposed
on contact/account fields; these rules follow `profile_flags.py` and
`source_prompt.py`, not the generic update endpoint's arbitrary JSON contract.

| Requirement / reusable scenario | Automated coverage |
| --- | --- |
| Clicking a value edits it in the detail view; label selection still opens evidence | `ReviewDraftPage.test.tsx`, `ReviewInbox.acceptance.test.tsx` |
| Every scalar, including absent/missing/conflicted values, is editable in draft/in_review | `ReviewDraftPage.test.tsx` |
| Other statuses stay read-only and still show evidence | `ReviewDraftPage.test.tsx` |
| Enter applies; Escape cancels current typing and restores focus; Tab/Shift+Tab and blur apply valid text; IME Enter does not apply | `InlineDraftField.test.tsx` |
| Blank list input retains text and an accessible error; correction or Escape clears it | `InlineDraftField.test.tsx`, `ReviewDraftPage.test.tsx` |
| Existing list indexes, neighboring entries, original evidence and unknown JSON are preserved | `draftEdits.test.ts`, `draftSources.test.ts`, `ReviewDraftPage.test.tsx` |
| Track original version identity, changed paths, original/current values and absent versus null keys; repeated edits compare to the loaded original | `draftEdits.test.ts` |
| Applied changes hide assessment-derived badges globally, label original evidence and mark edited values; full revert restores the original display | `ReviewDraftPage.test.tsx` |
| Conflicted scalar input starts empty rather than from joined alternatives; both original claims remain visible after correction | `ReviewDraftPage.test.tsx` |
| Original API reply is unchanged and editing sends no mutation request | `ReviewDraftPage.test.tsx`, `ReviewInbox.acceptance.test.tsx` |
| Leaving/reopening or opening another version resets applied edits, invalid text and dirty state | `ReviewInbox.acceptance.test.tsx` |

Paths above are under `frontend/src/` (helper), `frontend/src/components/`, or
`frontend/src/pages/` as appropriate. The production navigation tests reuse
`tests/fixtures/review_inbox/responses.json`; page tests use a synthetic draft with
missing and conflicting fields. Existing evidence, loading/error, retry and
late-response regressions remain in the page and source suites.

Run with Node 24 and locked dependencies, from `frontend`:

```bash
npm ci --ignore-scripts
npx vitest run src/draftEdits.test.ts src/components/InlineDraftField.test.tsx \
  src/components/draftSources.test.ts src/pages/ReviewDraftPage.test.tsx \
  src/pages/ReviewInbox.acceptance.test.tsx
npm test
npm run build
```

The local session stores `base` (client/profile/version IDs, version number and
created timestamp), `originalData`, `currentData`, and `changes[path]` with
`originalPresent`, `originalValue` and `currentValue`. Applied changes are separate
from editor callbacks: `onApply(path, text)`, `onPendingChange(path, {text, error} | null)`
and `onSelect()`. The page tracks pending fields separately, so a future save flow
can account for unapplied/invalid input. A full revert restores original key
presence. An empty edit on an absent or malformed scalar is a no-op, preserving
legacy data; a nonempty correction replaces only that field.

Assessment invalidation is display-only: saved assessment, conflicts, references
and approval metadata are not changed. Original evidence does not automatically
verify a reviewer correction. There is only an unsaved-local-changes notice, with
no navigation guard, browser storage, saving, recomputation or approval gate.

For #66, reuse these local scenarios after #60 adds save/reload, failures,
concurrent/stale saves, and approval of the edited version. Those persistence and
approval scenarios are intentionally not implemented by #59. In particular, #60
must choose a persistence/validation contract for corrected conflicts: the
source-draft validator requires conflicted scalar values to remain null and cannot
be used unchanged to save a corrected non-null value while retaining its original
conflict. Generic PUT also accepts arbitrary JSON and does not establish a current
assessment or a conflict-resolution guarantee.

Manual browser checks remain necessary for real Tab/Shift+Tab/blur focus movement,
IME behavior, visible focus and error announcement, long values and evidence,
and the responsive layout below 720px. jsdom interaction checks do not prove
browser layout, assistive-technology behavior or full #66 persistence acceptance.
