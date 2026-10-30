"""AT 2.2 (#46) and Task 2.2.2 (#29): given the same sample transcripts, when both
prompt versions are run, then paired outputs are saved and blinded for scoring.

The model is a unittest.mock stand-in, so CI needs no Ollama. The saved run in
tests/fixtures/comparison/run is checked as-is.
"""

import csv
import hashlib
import json
import random
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ai import ModelResponse, ProviderConfigError, ProviderUnavailable
from src.ai.compare import (
    VERSIONS,
    format_passes,
    main,
    name_correct,
    run_comparison,
    write_auto_scores,
)

FIXTURES = Path(__file__).parent / "fixtures"
TRANSCRIPTS = sorted(FIXTURES.glob("baseline/transcript_*.txt")) + sorted(
    (FIXTURES / "comparison").glob("transcript_*.txt")
)
BRAIN_FILE = FIXTURES / "brain" / "fa_systems_context.json"
EXPECTED_DIR = FIXTURES / "comparison" / "expected"
RUN_DIR = FIXTURES / "comparison" / "run"

BASELINE_REPLY = '{"name": "Maya Chen", "needs": ["more bookings"], "goals": []}'
BRAIN_REPLY = '{"name": "Maya Chen", "needs": ["more bookings"], "goals": ["30"]}'


def reply(text):
    return ModelResponse(text=text, provider="fake", model="fake-model", duration_ms=5)


def fake_provider():
    """Answers the Brain-assisted prompt and the baseline prompt differently."""
    provider = MagicMock()
    provider.name = "fake"
    provider.generate.side_effect = lambda prompt, **_: reply(
        BRAIN_REPLY if "FA Systems context:" in prompt else BASELINE_REPLY
    )
    return provider


def test_both_versions_get_the_same_transcripts_and_settings(tmp_path):
    provider = fake_provider()
    run_comparison(TRANSCRIPTS, tmp_path, provider, "## Terms", random.Random(1))

    calls = provider.generate.call_args_list
    assert len(calls) == 2 * len(TRANSCRIPTS)
    for transcript, (baseline, brain) in zip(
        TRANSCRIPTS, zip(calls[::2], calls[1::2], strict=True), strict=True
    ):
        text = transcript.read_text(encoding="utf-8")
        assert text in baseline.args[0] and text in brain.args[0]
        assert "FA Systems context:" not in baseline.args[0]
        assert "## Terms" in brain.args[0]
        assert baseline.kwargs == brain.kwargs == {"json_output": True}


def test_pairs_are_saved_and_blinded(tmp_path):
    key = run_comparison(
        TRANSCRIPTS, tmp_path, fake_provider(), "## Terms", random.Random(1)
    )

    assert list(key) == [path.stem for path in TRANSCRIPTS]
    for stem, labels in key.items():
        assert sorted(labels.values()) == sorted(VERSIONS)
        for label, version in labels.items():
            raw = (tmp_path / version / f"{stem}.raw.json").read_text()
            assert (tmp_path / "blinded" / f"{stem}.{label}.json").read_text() == raw
            assert (tmp_path / version / f"{stem}.meta.json").is_file()


def test_blinding_order_is_random_per_transcript(tmp_path):
    key = run_comparison(
        TRANSCRIPTS, tmp_path, fake_provider(), "## Terms", random.Random(1)
    )
    assert len({labels["A"] for labels in key.values()}) == 2


def test_malformed_reply_is_kept_for_scoring_not_retried(tmp_path):
    provider = MagicMock()
    provider.generate.return_value = reply("not json")

    key = run_comparison(
        TRANSCRIPTS[:1], tmp_path, provider, "## Terms", random.Random(1)
    )

    assert provider.generate.call_count == 2
    assert (tmp_path / "blinded" / "transcript_1.A.json").read_text() == "not json"
    assert key["transcript_1"]


def test_provider_errors_are_retried(tmp_path):
    provider = MagicMock()
    provider.generate.side_effect = [
        ProviderUnavailable("down"),
        reply(BASELINE_REPLY),
        reply(BRAIN_REPLY),
    ]
    run_comparison(TRANSCRIPTS[:1], tmp_path, provider, "## Terms", random.Random(1))
    assert provider.generate.call_count == 3


def test_provider_that_stays_down_fails_the_run(tmp_path):
    provider = MagicMock()
    provider.generate.side_effect = ProviderUnavailable("down")
    with pytest.raises(ProviderUnavailable):
        run_comparison(
            TRANSCRIPTS[:1], tmp_path, provider, "## Terms", random.Random(1), 2
        )
    assert provider.generate.call_count == 3


@pytest.mark.parametrize(
    ("text", "passes"),
    [
        ('{"name": null, "needs": [], "goals": []}', True),
        ('{"name": "A", "needs": ["x"], "goals": ["y"]}', True),
        ('{"name": "A", "needs": [], "goals": [], "budget": "5k"}', False),
        ('{"name": "A", "needs": []}', False),
        ('{"name": "A", "needs": "x", "goals": []}', False),
        ("```json\n{}\n```", False),
    ],
)
def test_format_check(text, passes):
    assert format_passes(text) is passes


@pytest.mark.parametrize(
    ("text", "expected", "correct"),
    [
        ('{"name": "Maya Chen"}', "Maya Chen", True),
        ('{"name": " Maya Chen "}', "Maya Chen", True),
        ('{"name": "Maya"}', "Maya Chen", False),
        ('{"name": null}', None, True),
        ('{"name": "null"}', None, False),
        ('{"name": "FA Systems"}', None, False),
        ("{}", None, False),
        ("[]", None, False),
        ("not json", "Maya Chen", False),
    ],
)
def test_name_check(text, expected, correct):
    assert name_correct(text, expected) is correct


def test_auto_scores_cover_every_blinded_output(tmp_path):
    key = run_comparison(
        TRANSCRIPTS, tmp_path, fake_provider(), "## Terms", random.Random(1)
    )
    with write_auto_scores(tmp_path, key, EXPECTED_DIR).open() as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 2 * len(TRANSCRIPTS)
    by_output = {(row["transcript"], row["output"]): row for row in rows}
    # Both fake replies are well formed; only transcript 1 is really Maya Chen.
    assert all(row["format_pass"] == "True" for row in rows)
    assert by_output[("transcript_1", "A")]["name_correct"] == "True"
    assert by_output[("transcript_2", "A")]["name_correct"] == "False"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A copy of the fixtures in a temp dir, used as the script's run directory."""
    shutil.copytree(
        FIXTURES, tmp_path / "fixtures", ignore=shutil.ignore_patterns("run")
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def cli_args(*extra):
    return [
        *(f"fixtures/{path.relative_to(FIXTURES)}" for path in TRANSCRIPTS),
        "--brain-context",
        "fixtures/brain/fa_systems_context.json",
        *extra,
    ]


def test_script_saves_key_metadata_and_auto_scores(workdir):
    with patch("src.ai.compare.get_provider", return_value=fake_provider()):
        code = main(
            cli_args(
                "--expected-dir", "fixtures/comparison/expected", "--out-dir", "out"
            )
        )

    assert code == 0
    out = workdir / "out"
    assert len(json.loads((out / "blinding_key.json").read_text())) == 6
    metadata = json.loads((out / "run_metadata.json").read_text())
    assert metadata["model"] == "fake-model"
    assert (
        metadata["brain_context"]["sha256"]
        == hashlib.sha256(BRAIN_FILE.read_bytes()).hexdigest()
    )
    assert len((out / "auto_scores.csv").read_text().splitlines()) == 13


def test_script_returns_1_when_the_provider_stays_down(workdir):
    provider = MagicMock()
    provider.generate.side_effect = ProviderUnavailable("down")
    with patch("src.ai.compare.get_provider", return_value=provider):
        assert main(cli_args("--out-dir", "out")) == 1
    assert not (workdir / "out" / "blinding_key.json").exists()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (cli_args("--expected-dir", "fixtures/brain"), "no reference answer for"),
        (cli_args("--out-dir", "../outside"), "is outside"),
        (
            ["fixtures/comparison/transcript_3.txt", *cli_args()],
            "would overwrite each other's outputs: transcript_3",
        ),
    ],
)
def test_script_refuses_bad_arguments_before_running(workdir, capsys, args, message):
    provider = fake_provider()
    with (
        patch("src.ai.compare.get_provider", return_value=provider),
        pytest.raises(SystemExit) as exit_info,
    ):
        main(args)
    assert exit_info.value.code == 2
    assert message in capsys.readouterr().err
    provider.generate.assert_not_called()


def test_script_refuses_invalid_brain_context(workdir, capsys):
    (workdir / "fixtures" / "brain" / "fa_systems_context.json").write_text("{}")
    with pytest.raises(SystemExit) as exit_info:
        main(cli_args())
    assert exit_info.value.code == 2
    assert "non-empty 'sections' list" in capsys.readouterr().err


def test_script_reports_a_missing_model_setting(workdir, capsys):
    error = ProviderConfigError("OLLAMA_MODEL is not set")
    with (
        patch("src.ai.compare.get_provider", side_effect=error),
        pytest.raises(SystemExit) as exit_info,
    ):
        main(cli_args())
    assert exit_info.value.code == 2
    assert "OLLAMA_MODEL is not set" in capsys.readouterr().err


# The saved real run (Ollama, llama3.2:3b) is the evidence for AT 2.2.


def test_saved_run_has_a_blinded_pair_for_every_transcript():
    key = json.loads((RUN_DIR / "blinding_key.json").read_text())
    assert list(key) == [path.stem for path in TRANSCRIPTS]
    for stem, labels in key.items():
        assert sorted(labels.values()) == sorted(VERSIONS)
        for label, version in labels.items():
            raw = (RUN_DIR / version / f"{stem}.raw.json").read_text()
            assert (RUN_DIR / "blinded" / f"{stem}.{label}.json").read_text() == raw


def test_saved_run_used_one_model_and_the_current_brain_context():
    metadata = json.loads((RUN_DIR / "run_metadata.json").read_text())
    models = {
        json.loads(path.read_text())["model"] for path in RUN_DIR.glob("*/*.meta.json")
    }
    assert models == {metadata["model"]}
    # Editing the Brain context after the run would make the saved pairs stale.
    assert (
        metadata["brain_context"]["sha256"]
        == hashlib.sha256(BRAIN_FILE.read_bytes()).hexdigest()
    )
