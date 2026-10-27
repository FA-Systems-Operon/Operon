"""US 2.2 (#30): the comparison sample, reference answers and scoring sheet agree.

See docs/evaluation/us-2.2-rubric.md for how these files are used.
"""

import csv
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED_DIR = FIXTURES / "comparison" / "expected"
SCORES = Path(__file__).parents[1] / "docs" / "evaluation" / "us-2.2-scores.csv"

# Transcripts 1-2 are the US 2.1 samples; 3-6 were added for US 2.2.
TRANSCRIPTS = sorted(FIXTURES.glob("baseline/transcript_*.txt")) + sorted(
    (FIXTURES / "comparison").glob("transcript_*.txt")
)
SCORERS = {"rimmch", "wassdak", "final"}


def load_expected(stem):
    return json.loads((EXPECTED_DIR / f"{stem}.expected.json").read_text())


def test_sample_has_six_uniquely_named_transcripts():
    stems = [path.stem for path in TRANSCRIPTS]
    assert stems == [f"transcript_{n}" for n in range(1, 7)]


def test_every_transcript_has_exactly_one_reference_answer():
    references = sorted(path.name for path in EXPECTED_DIR.glob("*.expected.json"))
    assert references == [f"{path.stem}.expected.json" for path in TRANSCRIPTS]


@pytest.mark.parametrize("transcript", TRANSCRIPTS, ids=lambda path: path.stem)
def test_reference_answer_shape(transcript):
    expected = load_expected(transcript.stem)
    assert set(expected) == {"name", "needs", "goals", "must_not_include"}
    assert expected["name"] is None or isinstance(expected["name"], str)
    for field in ("needs", "goals"):
        assert expected[field], f"{field} has no reference items"
    for field in ("needs", "goals", "must_not_include"):
        assert all(isinstance(item, str) and item for item in expected[field])


@pytest.mark.parametrize("transcript", TRANSCRIPTS, ids=lambda path: path.stem)
def test_reference_name_is_stated_in_transcript(transcript):
    name = load_expected(transcript.stem)["name"]
    if name is not None:
        assert name in transcript.read_text(encoding="utf-8")


def test_scoring_sheet_has_one_row_per_transcript_output_and_scorer():
    with SCORES.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    keys = [(row["transcript"], row["output"], row["scorer"]) for row in rows]
    assert len(keys) == len(set(keys)), "duplicate rows"
    assert set(keys) == {
        (path.stem, output, scorer)
        for path in TRANSCRIPTS
        for output in ("A", "B")
        for scorer in SCORERS
    }


def test_scoring_sheet_counts_match_reference_items():
    with SCORES.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            expected = load_expected(row["transcript"])
            items = len(expected["needs"]) + len(expected["goals"])
            assert int(row["items_expected"]) == items, row["transcript"]
