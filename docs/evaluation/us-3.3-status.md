# US 3.3 / AT 3.3 verification

## Result

The Ollama availability and real-model verification gap is resolved. The final
production prompt/generation path passed all eight regression cases on November
2, 2026. Every case used one model call, with no missed/extra missing-field flags,
missed/extra conflict flags, or incorrect expected conflict alternatives. The
original five cases' scalar values also match their reference facts. A later
ninth case currently fails; see the follow-up section below.

Evidence:

- `us-3.3-qwen25-14b-results.json`: sources, expected/observed flags, validated
  drafts, prompt/schema hashes, call counts, model and durations for all eight cases.
- `us-3.3-runtime.json`: Ollama version, exact model digest and runtime settings.
- `us-3.3-live-jobs.txt`: three actual-provider tests passed through uploads,
  UUID source documents, onboarding jobs, immutable persistence and API retrieval.
- `us-3.3-live-goals-job.txt`: the affected goals job passed again after the final
  compatibility-prompt correction.
- `us-3.3-initial-live-summary.json`: the initial fresh run passed seven cases and
  falsely flagged compatible goals. The answer key was retained; the prompt was
  corrected to distinguish compatible list items from incompatible scalar claims.
- `us-3.3-qwen25-14b-field-meanings-results.json`: the nine-case run after the
  field-meaning correction below. The original eight cases passed again; the new
  ninth case is a known failure.

## Follow-up: ambiguous `business_number` (November 2, 2026)

A manual end-to-end check through the running stack found a reproducible failure
the eight cases did not cover. The transcript gave a main line of 514-555-0100,
the intake gave `Phone number: 514-555-0199`, and neither document stated a
business number. The onboarding job failed 4 of 4 times with no draft saved.

Captured replies showed `qwen2.5:14b` read "business number" as the business's
phone number. It filed the phone conflict under `business_number`, with both
phone numbers as alternatives. The validator correctly rejected both the first
reply and the repair, so no mislabeled draft was saved. The prompt previously
named the fields without defining them. Every existing case uses `BN-…` or
`NEQ-…` values, which cannot be mistaken for phone numbers.

Correction: the prompt now gives a one-line meaning for the ambiguous fields.
`business_number` is a government registration or tax number and never a phone
number; `phone_number` includes main and business lines. A conflict must be
filed under the field its alternative values belong to. The answer key of
existing cases is unchanged. A ninth case, `phone_conflict_without_business_number`,
covers this input.

Result with `qwen2.5:14b`:

- The original eight cases all passed again, each with one model call.
- The ninth case now files the phone conflict under `phone_number` and correctly
  reports `business_number` missing. It still **fails**: the model left `email`
  and `business_address` null although the intake states both, so they are
  falsely reported missing. In the equivalent uploaded-document job, the model
  instead quoted `Our website is …`, which the transcript does not contain, and
  validation rejected the draft. These are model accuracy gaps, not validator
  defects. The case is kept as a known failure, so the evaluation script exits
  nonzero until it passes.
- Default backend suite: 585 passed, five live tests skipped.

## Scope and environment

The implementation uses the nine mandatory onboarding fields confirmed by the
user. Name, needs and goals remain supported but are not required for completeness.
The existing review component is extended; the full review page remains #57.

Ollama 0.40.13 is running as a per-user, localhost-only service. Local evaluation
uses `qwen2.5:14b` (Q4_K_M), context 8192, temperature 0, seed 42, with cloud
features disabled. No further model installation is needed on this machine.
The ignored local `.env` selects the tested model. It leaves the base URL unset:
host-side evaluation uses the backend's localhost default, while Compose retains
its existing host-service alias default. The full application stack is not newly
configured by these tests.

## Checks and reproduction

- Default backend suite: 585 passed, five live tests skipped in the CI-style run.
- Frontend: 31 tests passed and the TypeScript/Vite build passed.
  The component now has scoped dark styles matching the UI branch tokens,
  responsive field rows, attributed citations via host-provided document labels,
  and distinct wording for unresolved conflicts. Both source links are preserved.
  The user approved the desktop appearance from a manual browser preview.
- Repository Ruff lint and formatting passed.
- Three live job tests were run explicitly, separately from model-free CI.

From the repo root, with the backend dependencies installed and Ollama running:

```bash
OLLAMA_MODEL=qwen2.5:14b OLLAMA_BASE_URL=http://127.0.0.1:11434 \
OLLAMA_TIMEOUT_SECONDS=180 PYTHONPATH=backend \
  .venv/bin/python scripts/evaluate_profile_flags.py > /tmp/operon-flags-evaluation.json
```

The live job command additionally needs `RUN_OLLAMA_TESTS=1` and a dedicated
`TEST_DATABASE_URL` ending in `_test`; see `tests/README.md`.

## Validation boundaries

Schema-constrained output controls structure and allowed document IDs. The server
independently validates quotes, field paths, document kinds and client ownership.
Generation can complete references from exact scalar-value occurrences and align
terminal punctuation only when the resulting quote is present in the same source.
One model repair is allowed; a second invalid reply fails without saving a draft.

The nine cases were used during development. They are regression cases, not an
independent held-out accuracy study or a guarantee for arbitrary client documents.
Quote matching proves provenance, not semantic correctness. Reviewers still
resolve potential conflicts and assess the source interpretation.

UI tests verify the reusable component and keyboard navigation. The user reviewed
the desktop preview and supplied screenshots showing the styled fields and a
source passage opened with the selected quote highlighted. This is manual
component-level review, not automated browser testing. On November 2, 2026, the
user also confirmed that both guided browser checks passed: narrow-window layout
across all three scenarios, and keyboard navigation/focus, source activation and
return to the scenario selector. The full review-page workflow and its styled
evidence panel remain #57.
PR review and stakeholder sign-off are not replaced by these test results.
