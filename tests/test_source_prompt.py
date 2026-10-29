"""Task #39: source-aware prompts preserve inputs and define usable evidence."""

import json

import pytest
from pydantic import ValidationError

from src.ai.source_prompt import (
    SourceInput,
    SourceLinkedProfile,
    build_source_profile_prompt,
)


def test_prompt_contains_both_sources_and_separates_brain_context():
    sources = [
        SourceInput(document_id="doc-1", kind="transcript", text='Maya: "More calls."'),
        SourceInput(document_id="doc-2", kind="intake", text="Goal: 20 bookings.\n月"),
    ]
    prompt = build_source_profile_prompt(sources, "Business context {only}")
    encoded_sources = prompt.split("Source documents (JSON):\n", 1)[1]
    assert json.loads(encoded_sources) == [source.model_dump() for source in sources]
    assert '"Business context {only}"' in prompt
    assert "not evidence for client facts" in prompt
    assert "every needs/goals item must have evidence" in prompt


def test_prompt_rejects_missing_or_ambiguous_sources():
    source = SourceInput(document_id="doc-1", kind="transcript", text="Hello")
    with pytest.raises(ValueError, match="At least one"):
        build_source_profile_prompt([])
    with pytest.raises(ValueError, match="unique"):
        build_source_profile_prompt([source, source])


def test_response_format_preserves_item_level_references():
    profile = SourceLinkedProfile.model_validate(
        {
            "name": None,
            "needs": ["More calls"],
            "goals": [],
            "source_references": [
                {"field": "needs/0", "document_id": "doc-1", "quote": "More calls"}
            ],
        }
    )
    assert profile.model_dump()["source_references"][0]["field"] == "needs/0"


@pytest.mark.parametrize("field", ["budget", "needs/-1", "needs/01", "goals/x"])
def test_response_format_rejects_invalid_field_paths(field):
    with pytest.raises(ValidationError):
        SourceLinkedProfile.model_validate(
            {
                "name": None,
                "needs": [],
                "goals": [],
                "source_references": [
                    {"field": field, "document_id": "doc-1", "quote": "evidence"}
                ],
            }
        )
