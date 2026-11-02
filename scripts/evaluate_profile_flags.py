"""Run the #49 synthetic cases against the configured provider, outside CI.

PYTHONPATH=backend .venv/bin/python scripts/evaluate_profile_flags.py > /tmp/flags-evaluation.json
Only synthetic documents are sent. Nonzero exit means errors or answer-key mismatches.
A passing report is a small regression sample, not a general accuracy guarantee.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.ai.provider import ProviderError, get_provider
from src.ai.source_prompt import (
    SourceInput,
    build_source_profile_prompt,
    parse_source_profile,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cases = json.loads(
        (ROOT / "tests/fixtures/onboarding_flags/cases.json").read_text()
    )
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
            SourceInput(document_id=kind, kind=kind, text=text)
            for kind, text in case["documents"].items()
        ]
        prompt = build_source_profile_prompt(sources)
        result = {
            "case": case["id"],
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "expected": case["expected"],
        }
        try:
            reply = provider.generate(prompt, json_output=True)
            result.update(
                provider=reply.provider,
                model=reply.model,
                duration_ms=reply.duration_ms,
            )
            draft = parse_source_profile(reply.text, sources)
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
            actual_email_values = {
                alternative.value
                for conflict in draft.conflicts
                if conflict.field == "email"
                for alternative in conflict.alternatives
            }
            result["alternative_values_match"] = actual_email_values == set(
                case["expected"]["email_values"]
            )
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
        report["cases"].append(result)
    report["passed"] = all(case["passed"] for case in report["cases"])
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
