"""Run the #49 synthetic cases against the configured provider, outside CI.

PYTHONPATH=backend .venv/bin/python scripts/evaluate_profile_flags.py > /tmp/flags-evaluation.json
Only synthetic documents are sent. Nonzero exit means errors or answer-key mismatches.
A passing report is a small regression sample, not a general accuracy guarantee.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.ai.provider import ModelProvider, ModelResponse, ProviderError, get_provider
from src.ai.source_prompt import (
    SourceInput,
    build_source_profile_prompt,
    generate_source_profile,
    source_profile_schema,
)

ROOT = Path(__file__).resolve().parents[1]


def load_cases() -> list[dict]:
    directory = ROOT / "tests/fixtures/onboarding_flags"
    return [
        case
        for filename in ("cases.json", "additional_cases.json")
        for case in json.loads((directory / filename).read_text())
    ]


class EvaluationProvider:
    """Observe the production generation path without replacing its behavior."""

    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.responses: list[ModelResponse] = []
        self.prompt_hashes: list[str] = []

    def generate(self, prompt: str, **kwargs) -> ModelResponse:
        self.prompt_hashes.append(hashlib.sha256(prompt.encode()).hexdigest())
        response = self.provider.generate(prompt, **kwargs)
        self.responses.append(response)
        return response


def main() -> int:
    cases = load_cases()
    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "cases": [],
    }
    try:
        provider = get_provider()
    except ProviderError as error:
        report.update(status="unavailable", error=type(error).__name__)
        print(json.dumps(report, indent=2))
        return 1
    for case in cases:
        sources = [
            SourceInput(
                document_id=str(
                    uuid.uuid5(uuid.NAMESPACE_URL, case["id"] + "/" + kind)
                ),
                kind=kind,
                text=text,
            )
            for kind, text in case["documents"].items()
        ]
        prompt = build_source_profile_prompt(sources)
        observed = EvaluationProvider(provider)
        result = {
            "case": case["id"],
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "expected": case["expected"],
            "sources": [source.model_dump() for source in sources],
            "schema_sha256": hashlib.sha256(
                json.dumps(source_profile_schema(sources), sort_keys=True).encode()
            ).hexdigest(),
        }
        try:
            draft = generate_source_profile(sources, observed)
            actual_missing = set(draft.assessment.missing_fields)
            actual_conflicts = {conflict.field for conflict in draft.conflicts}
            expected_missing = set(case["expected"]["missing_fields"])
            expected_conflicts = set(case["expected"]["conflict_fields"])
            result.update(
                missed_missing=sorted(expected_missing - actual_missing),
                false_missing=sorted(actual_missing - expected_missing),
                missed_conflicts=sorted(expected_conflicts - actual_conflicts),
                false_conflicts=sorted(actual_conflicts - expected_conflicts),
                draft=draft.model_dump(),
            )
            actual_values = {
                conflict.field: sorted(
                    alternative.value for alternative in conflict.alternatives
                )
                for conflict in draft.conflicts
            }
            expected_values = case["expected"].get("conflict_values", {})
            if case["expected"].get("email_values"):
                expected_values = {"email": case["expected"]["email_values"]}
            result["alternative_values_match"] = actual_values == {
                field: sorted(values) for field, values in expected_values.items()
            }
            result["passed"] = result["alternative_values_match"] and not any(
                result[key]
                for key in (
                    "missed_missing",
                    "false_missing",
                    "missed_conflicts",
                    "false_conflicts",
                )
            )
        except (ProviderError, ValueError) as error:
            # No raw response/error body is logged. Only controlled synthetic
            # successful drafts are included in this local report.
            result.update(passed=False, error=type(error).__name__)
        result["model_calls"] = len(observed.prompt_hashes)
        result["attempt_prompt_sha256"] = observed.prompt_hashes
        if observed.responses:
            last = observed.responses[-1]
            result.update(
                provider=last.provider,
                model=last.model,
                duration_ms=sum(
                    response.duration_ms for response in observed.responses
                ),
            )
        report["cases"].append(result)
    report["passed"] = all(case["passed"] for case in report["cases"])
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
