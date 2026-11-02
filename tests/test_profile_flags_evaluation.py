"""The optional model evaluation must distinguish success, mismatch and outage."""

import json
import sys

import pytest
from scripts import evaluate_profile_flags as evaluation

from src.ai.provider import ModelResponse, ProviderConfigError, ProviderUnavailable


@pytest.mark.parametrize(
    "mode", ["correct", "missed_conflict", "invalid_output", "unavailable"]
)
def test_evaluation_records_observed_results_and_exit_status(
    monkeypatch, tmp_path, mode
):
    cases = json.loads(
        (evaluation.ROOT / "tests/fixtures/onboarding_flags/cases.json").read_text()
    )

    class Provider:
        def generate(self, prompt, *, json_output):
            assert json_output
            if mode == "unavailable":
                raise ProviderUnavailable("offline")
            sources = json.loads(prompt.split("Source documents (JSON):\n", 1)[1])
            documents = {source["kind"]: source["text"] for source in sources}
            case = next(case for case in cases if case["documents"] == documents)
            payload = {**case["reply"]}
            if mode == "missed_conflict":
                payload["conflicts"] = []
            text = "invalid JSON" if mode == "invalid_output" else json.dumps(payload)
            return ModelResponse(text, "fake", "evaluation-test", 1)

    monkeypatch.setattr(evaluation, "get_provider", lambda: Provider())
    output = tmp_path / "evaluation.json"
    monkeypatch.setattr(
        sys, "argv", ["evaluate_profile_flags", "--output", str(output)]
    )
    code = evaluation.main()
    report = json.loads(output.read_text())
    assert code == (0 if mode == "correct" else 1)
    assert report["passed"] is (mode == "correct")
    assert len(report["cases"]) == 5
    if mode == "missed_conflict":
        assert report["cases"][0]["missed_conflicts"] == ["email"]
        assert report["cases"][0]["alternative_values_match"] is False
        assert report["cases"][2]["passed"] is True
    elif mode in {"invalid_output", "unavailable"}:
        assert all("error" in case for case in report["cases"])
    else:
        assert all(len(case["prompt_sha256"]) == 64 for case in report["cases"])
        assert all(case["model"] == "evaluation-test" for case in report["cases"])


def test_missing_provider_configuration_is_reported_as_unavailable(
    monkeypatch, tmp_path
):
    def unconfigured():
        raise ProviderConfigError("no model")

    monkeypatch.setattr(evaluation, "get_provider", unconfigured)
    output = tmp_path / "evaluation.json"
    monkeypatch.setattr(
        sys, "argv", ["evaluate_profile_flags", "--output", str(output)]
    )
    assert evaluation.main() == 1
    report = json.loads(output.read_text())
    assert report["status"] == "unavailable"
    assert report["error"] == "ProviderConfigError"
    assert report["cases"] == []
