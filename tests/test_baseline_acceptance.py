"""AT 2.1 (#45): Given a fake sample transcript, when the baseline script runs,
then it returns a client profile with name, needs and goals, and the output is saved.

The model is faked so CI needs no Ollama. The saved #26 outputs are checked
as-is. Set RUN_OLLAMA_TESTS=1 (plus OLLAMA_MODEL) to also run it for real.
"""

import json
import os
from pathlib import Path

import pytest

from src.ai import ModelResponse
from src.ai.baseline import BaselineOutputError, parse_client_profile, run_baseline

BASELINE_DIR = Path(__file__).parent / "fixtures" / "baseline"
TRANSCRIPTS = sorted(BASELINE_DIR.glob("transcript_*.txt"))
# The speaker named in each synthetic transcript.
EXPECTED_NAMES = {"transcript_1": "Maya Chen", "transcript_2": "Jordan Patel"}


class FakeProvider:
    """Replies with a fixed text and records every prompt it was sent."""

    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate(self, prompt, *, system=None, json_output=False):
        self.calls.append({"prompt": prompt, "json_output": json_output})
        return ModelResponse(
            text=self.text, provider="fake", model="fake-model", duration_ms=5
        )


def assert_client_profile(profile, expected_name):
    assert profile["name"] == expected_name
    for field in ("needs", "goals"):
        assert profile[field], f"{field} is empty"
        assert all(value.strip() for value in profile[field])


def test_fixture_transcripts_exist():
    assert {path.stem for path in TRANSCRIPTS} == set(EXPECTED_NAMES)


@pytest.mark.parametrize("transcript", TRANSCRIPTS, ids=lambda path: path.stem)
def test_baseline_script_returns_and_saves_profile(transcript, tmp_path):
    raw_reply = (BASELINE_DIR / f"{transcript.stem}.raw.json").read_text("utf-8")
    provider = FakeProvider(raw_reply)

    result = run_baseline(transcript, tmp_path, provider)

    # The transcript went to the model inside the baseline prompt, as JSON mode.
    [call] = provider.calls
    assert transcript.read_text("utf-8") in call["prompt"]
    assert call["json_output"] is True
    # It returns a client profile with name, needs and goals.
    assert_client_profile(result.profile, EXPECTED_NAMES[transcript.stem])
    # And the output is saved: the untouched reply plus run metadata.
    assert result.raw_path == tmp_path / f"{transcript.stem}.raw.json"
    assert result.raw_path.read_text("utf-8") == raw_reply
    meta = json.loads(result.meta_path.read_text("utf-8"))
    assert meta["transcript"] == transcript.name
    assert meta["model"] == "fake-model"


@pytest.mark.parametrize("transcript", TRANSCRIPTS, ids=lambda path: path.stem)
def test_saved_baseline_output_is_a_client_profile(transcript):
    """The #26 run outputs on disk meet the same bar, without rerunning the model."""
    raw = (BASELINE_DIR / f"{transcript.stem}.raw.json").read_text("utf-8")

    profile = parse_client_profile(raw)

    assert_client_profile(profile, EXPECTED_NAMES[transcript.stem])
    assert profile["name"] in transcript.read_text("utf-8")


def test_saved_run_metadata_records_model_and_settings():
    metadata = (BASELINE_DIR / "run_metadata.md").read_text("utf-8")
    for expected in ("llama3.2:3b", "Temperature: 0", "Seed: 42"):
        assert expected in metadata


def test_malformed_reply_is_saved_then_rejected(tmp_path):
    reply = '{"name": "Maya Chen", "needs": []}'

    with pytest.raises(BaselineOutputError, match="goals"):
        run_baseline(TRANSCRIPTS[0], tmp_path, FakeProvider(reply))

    assert (tmp_path / "transcript_1.raw.json").read_text("utf-8") == reply


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "[]",
        '{"name": 3, "needs": [], "goals": []}',
        '{"name": null, "needs": "x", "goals": []}',
        '{"name": null, "needs": [], "goals": [1]}',
    ],
)
def test_parse_client_profile_rejects_wrong_shape(reply):
    with pytest.raises(BaselineOutputError):
        parse_client_profile(reply)


def test_parse_client_profile_allows_missing_name():
    profile = parse_client_profile('{"name": null, "needs": [], "goals": []}')
    assert profile["name"] is None


@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_TESTS") != "1", reason="set RUN_OLLAMA_TESTS=1 to call Ollama"
)
@pytest.mark.parametrize("transcript", TRANSCRIPTS, ids=lambda path: path.stem)
def test_baseline_script_with_real_model(transcript, tmp_path):
    from src.ai import get_provider

    result = run_baseline(transcript, tmp_path, get_provider())

    assert_client_profile(result.profile, EXPECTED_NAMES[transcript.stem])
    assert result.raw_path.exists()
