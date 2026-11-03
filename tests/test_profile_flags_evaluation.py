"""The optional model evaluation must distinguish success, mismatch and outage."""

import json
import runpy

import pytest
from scripts import evaluate_profile_flags as evaluation

from src.ai.provider import ModelResponse, ProviderConfigError, ProviderUnavailable


@pytest.mark.parametrize(
    "mode", ["correct", "missed_conflict", "invalid_output", "unavailable"]
)
def test_evaluation_records_observed_results_and_exit_status(monkeypatch, capsys, mode):
    cases = json.loads(
        (evaluation.ROOT / "tests/fixtures/onboarding_flags/cases.json").read_text()
    )

    class Provider:
        def generate(self, prompt, *, json_output, output_schema):
            assert json_output
            if mode == "unavailable":
                raise ProviderUnavailable("offline")
            sources = json.loads(prompt.split("Source documents (JSON):\n", 1)[1])
            documents = {source["kind"]: source["text"] for source in sources}
            case = next(case for case in cases if case["documents"] == documents)
            from tests.test_profile_flags_acceptance import bind_documents

            payload = bind_documents(
                case["reply"],
                {source["kind"]: source["document_id"] for source in sources},
            )
            assert output_schema["required"]
            if mode == "missed_conflict":
                payload["conflicts"] = []
            text = "invalid JSON" if mode == "invalid_output" else json.dumps(payload)
            return ModelResponse(text, "fake", "evaluation-test", 1)

    monkeypatch.setattr(evaluation, "load_cases", lambda: cases)
    monkeypatch.setattr(evaluation, "get_provider", lambda: Provider())
    code = evaluation.main()
    report = json.loads(capsys.readouterr().out)
    assert code == (0 if mode == "correct" else 1)
    assert report["passed"] is (mode == "correct")
    assert len(report["cases"]) == 5
    assert all(
        case["model_calls"] == (2 if mode == "invalid_output" else 1)
        for case in report["cases"]
    )
    if mode == "missed_conflict":
        assert report["cases"][0]["missed_conflicts"] == ["email"]
        assert report["cases"][0]["alternative_values_match"] is False
        assert report["cases"][2]["passed"] is True
    elif mode in {"invalid_output", "unavailable"}:
        assert all("error" in case for case in report["cases"])
    else:
        assert all(len(case["prompt_sha256"]) == 64 for case in report["cases"])
        assert all(case["model"] == "evaluation-test" for case in report["cases"])


def test_missing_provider_configuration_is_reported_as_unavailable(monkeypatch, capsys):
    def unconfigured():
        raise ProviderConfigError("no model")

    monkeypatch.setattr(evaluation, "get_provider", unconfigured)
    assert evaluation.main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "unavailable"
    assert report["error"] == "ProviderConfigError"
    assert report["cases"] == []


def test_command_entrypoint_reports_unavailable_provider(monkeypatch, capsys):
    def unconfigured():
        raise ProviderConfigError("no model")

    monkeypatch.setattr("src.ai.provider.get_provider", unconfigured)
    with pytest.raises(SystemExit) as error:
        runpy.run_path(
            str(evaluation.ROOT / "scripts/evaluate_profile_flags.py"),
            run_name="__main__",
        )
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


def test_fixed_evaluation_set_includes_independent_prose_and_formatting_cases():
    cases = evaluation.load_cases()
    assert len(cases) == 9
    assert {case["id"] for case in cases} >= {
        "phone_conflict_prose",
        "equivalent_phone_formatting",
        "intake_adds_no_information",
        "phone_conflict_without_business_number",
    }
