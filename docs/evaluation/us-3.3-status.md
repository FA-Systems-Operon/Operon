# US 3.3 / AT 3.3 evaluation status

Implementation uses the nine mandatory onboarding fields confirmed by the user.
Automated tests use synthetic data and a fake provider; they exercise schema and
evidence validation, the actual onboarding job, immutable persistence, retrieval,
and the existing frontend component.

Real-model evaluation is **pending**, not passed. On November 2, 2026, the local
Ollama endpoint at `localhost:11434` was unreachable. The evaluation runner also
reported `ProviderConfigError` because `OLLAMA_MODEL` was not set in its process.
No model was installed or downloaded for this task. Run
`scripts/evaluate_profile_flags.py` using the documented environment settings once
the project's provider is available, inspect the generated report, and record
misses and false positives before claiming semantic detection quality.

The controlled cases and answer keys are fixed in
`tests/fixtures/onboarding_flags/cases.json`. The report compares missing/conflict
fields and email alternatives, and includes the model and prompt hash for each
case. These cases do not establish a general accuracy threshold. Evidence quote
matching proves provenance, not that two claims actually contradict one another.

The full review-page workflow remains #57; component tests do not establish a
browser end-to-end flow. Automated keyboard focus checks pass. A visual preview
was prepared but could not be inspected because no browser surface was available
to the session; temporary preview files/server were removed afterward.
