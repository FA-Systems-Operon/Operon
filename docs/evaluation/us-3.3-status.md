# US 3.3 / AT 3.3 verification

## Result

The Ollama availability and real-model verification gap is resolved. The final
production prompt/generation path passed all eight regression cases on November
2, 2026. Every case used one model call, with no missed/extra missing-field flags,
missed/extra conflict flags, or incorrect expected conflict alternatives. The
original five cases' scalar values also match their reference facts.

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
- Frontend: 29 tests passed and the TypeScript/Vite build passed.
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

The eight cases were used during development. They are regression cases, not an
independent held-out accuracy study or a guarantee for arbitrary client documents.
Quote matching proves provenance, not semantic correctness. Reviewers still
resolve potential conflicts and assess the source interpretation.

UI tests verify the reusable component and keyboard navigation. Browser visual
inspection has not been completed; the full review-page workflow remains #57.
PR review and stakeholder sign-off are not replaced by these test results.
