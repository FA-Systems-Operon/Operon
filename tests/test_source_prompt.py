"""Task #39: source-aware prompts preserve inputs and define usable evidence."""

import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from src.ai.provider import ModelResponse, ProviderUnavailable
from src.ai.source_prompt import (
    SourceInput,
    SourceLinkedProfile,
    build_source_profile_prompt,
    generate_source_profile,
    parse_source_profile,
    source_profile_schema,
    validate_generated_profile,
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


@pytest.fixture
def evidence_case():
    sources = [
        SourceInput(document_id="call", kind="transcript", text="Maya: I need calls."),
        SourceInput(document_id="form", kind="intake", text="Target: 20 bookings."),
    ]
    profile = {
        "name": "Maya",
        "needs": ["More calls"],
        "goals": ["20 bookings"],
        "source_references": [
            {"field": "name", "document_id": "call", "quote": "Maya"},
            {"field": "needs/0", "document_id": "call", "quote": "I need calls."},
            {"field": "goals/0", "document_id": "form", "quote": "20 bookings."},
        ],
    }
    return sources, profile


def test_parser_accepts_evidence_from_transcript_and_intake(evidence_case):
    sources, profile = evidence_case
    result = parse_source_profile(json.dumps(profile), sources).model_dump()
    assert {key: result[key] for key in profile} == profile
    assert len(result["assessment"]["missing_fields"]) == 9


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"document_id": "unknown"}, "unknown source"),
        ({"document_id": "form"}, "occur exactly"),
        ({"quote": "Invented passage"}, "occur exactly"),
        ({"quote": " "}, "occur exactly"),
        ({"field": "needs/1"}, "absent field"),
    ],
)
def test_parser_rejects_invalid_evidence(evidence_case, change, message):
    sources, profile = evidence_case
    profile["source_references"][0].update(change)
    with pytest.raises(ValueError, match=message):
        parse_source_profile(json.dumps(profile), sources)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_parser_requires_evidence_for_every_populated_item(evidence_case, index):
    sources, profile = evidence_case
    profile["source_references"].pop(index)
    with pytest.raises(ValueError, match="Missing source references"):
        parse_source_profile(json.dumps(profile), sources)


def test_unknown_information_needs_no_evidence(evidence_case):
    sources, _ = evidence_case
    profile = {"name": None, "needs": [], "goals": [], "source_references": []}
    assert parse_source_profile(json.dumps(profile), sources).name is None
    profile["source_references"] = [
        {"field": "name", "document_id": "call", "quote": "Maya"}
    ]
    with pytest.raises(ValueError, match="absent field"):
        parse_source_profile(json.dumps(profile), sources)


@pytest.mark.parametrize("text", ["not json", "{}", '{"name": 42}'])
def test_parser_rejects_malformed_model_output(evidence_case, text):
    sources, _ = evidence_case
    with pytest.raises(ValidationError):
        parse_source_profile(text, sources)


def test_generation_returns_validated_profile(evidence_case):
    sources, profile = evidence_case
    provider = Mock()
    provider.generate.return_value = ModelResponse(
        json.dumps(profile), "fake", "fake", 1
    )
    result = generate_source_profile(sources, provider, "Context only")
    assert {key: result.model_dump()[key] for key in profile} == profile
    provider.generate.assert_called_once_with(
        build_source_profile_prompt(sources, "Context only"),
        json_output=True,
        output_schema=source_profile_schema(sources),
    )


def test_generation_rejects_invalid_evidence_without_retry(evidence_case):
    sources, profile = evidence_case
    profile["source_references"][0]["quote"] = "Invented quote"
    provider = Mock()
    provider.generate.return_value = ModelResponse(
        json.dumps(profile), "fake", "fake", 1
    )
    with pytest.raises(ValueError, match="occur exactly"):
        generate_source_profile(sources, provider)
    provider.generate.assert_called_once()


def test_generation_propagates_provider_failure(evidence_case):
    sources, _ = evidence_case
    provider = Mock()
    provider.generate.side_effect = ProviderUnavailable("offline")
    with pytest.raises(ProviderUnavailable, match="offline"):
        generate_source_profile(sources, provider)
    provider.generate.assert_called_once()


def test_generation_checks_sources_before_calling_provider():
    provider = Mock()
    with pytest.raises(ValueError, match="At least one"):
        generate_source_profile([], provider)
    provider.generate.assert_not_called()


@pytest.mark.parametrize("field", ["name", "needs", "goals"])
def test_parser_rejects_blank_profile_values(evidence_case, field):
    sources, profile = evidence_case
    profile[field] = " " if field == "name" else [" "]
    with pytest.raises(ValueError, match="blank"):
        parse_source_profile(json.dumps(profile), sources)


def test_decoding_schema_requires_all_fields_and_pins_reference_ids(evidence_case):
    sources, _ = evidence_case
    schema = source_profile_schema(sources)
    assert set(schema["required"]) == set(schema["properties"])
    for name in ("SourceReference", "ConflictAlternative"):
        assert schema["$defs"][name]["properties"]["document_id"]["enum"] == [
            "call",
            "form",
        ]
    for field in ("needs", "goals"):
        with pytest.raises(ValidationError):
            SourceLinkedProfile.model_validate(
                {
                    "name": None,
                    "needs": [],
                    "goals": [],
                    "source_references": [
                        {"field": field, "document_id": "call", "quote": "text"}
                    ],
                }
            )


def test_generated_literal_scalars_get_exact_evidence_but_api_validation_stays_strict():
    sources = [
        SourceInput(
            document_id="call",
            kind="transcript",
            text="Name: Maya; Email: maya@example.test",
        )
    ]
    payload = {
        "name": "Maya",
        "email": "maya@example.test",
        "needs": [],
        "goals": [],
        "source_references": [],
    }
    with pytest.raises(ValueError, match="Missing source references"):
        parse_source_profile(json.dumps(payload), sources)
    draft = validate_generated_profile(json.dumps(payload), sources)
    assert [
        (ref.field, ref.quote, ref.document_id) for ref in draft.source_references
    ] == [
        ("name", "Maya", "call"),
        ("email", "maya@example.test", "call"),
    ]
    payload["email"] = "unsupported@example.test"
    with pytest.raises(ValueError, match="Missing source references"):
        validate_generated_profile(json.dumps(payload), sources)


def test_generation_never_replaces_fabricated_existing_evidence(evidence_case):
    sources, payload = evidence_case
    payload["source_references"][0]["quote"] = "Fabricated quote"
    with pytest.raises(ValueError, match="occur exactly"):
        validate_generated_profile(json.dumps(payload), sources)


def test_generated_redundant_conflict_references_are_deduplicated_only_after_validation():
    sources = [
        SourceInput(
            document_id="call", kind="transcript", text="Email: one@example.test"
        ),
        SourceInput(document_id="form", kind="intake", text="Email: two@example.test"),
    ]
    alternatives = [
        {"value": "one@example.test", "document_id": "call", "quote": sources[0].text},
        {"value": "two@example.test", "document_id": "form", "quote": sources[1].text},
    ]
    payload = {
        "name": None,
        "needs": [],
        "goals": [],
        "email": None,
        "source_references": [
            {"field": "email", "document_id": "call", "quote": sources[0].text}
        ],
        "conflicts": [
            {
                "field": "email",
                "explanation": "Different contact email",
                "alternatives": alternatives,
            }
        ],
    }
    draft = validate_generated_profile(json.dumps(payload), sources)
    assert draft.source_references == []
    assert draft.conflicts[0].model_dump()["alternatives"] == alternatives
    payload["source_references"][0]["quote"] = "Unrelated quote"
    with pytest.raises(ValueError, match="absent field"):
        validate_generated_profile(json.dumps(payload), sources)
    payload["conflicts"][0]["alternatives"][0]["quote"] = "Invented quote"
    with pytest.raises(ValueError, match="occur exactly"):
        validate_generated_profile(json.dumps(payload), sources)
