"""Task 2.2.1 (#28): the Brain-assisted prompt adds FA Systems context to the
baseline prompt and changes nothing else except the rule that forbade it.
"""

import difflib
import importlib
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ai import brain_prompt
from src.ai.baseline_prompt import build_baseline_client_profile_prompt
from src.ai.brain_prompt import (
    BASELINE_CONTEXT_RULE,
    BRAIN_CONTEXT_RULE,
    build_brain_assisted_client_profile_prompt,
    load_brain_context,
    render_brain_context,
)

BRAIN_FILE = Path(__file__).parent / "fixtures" / "brain" / "fa_systems_context.json"
TRANSCRIPT = "Client onboarding call\n\nMaya Chen: I need more bookings."


def test_only_the_context_section_and_one_rule_differ_from_baseline():
    context = load_brain_context(BRAIN_FILE)
    baseline = build_baseline_client_profile_prompt(TRANSCRIPT).splitlines()
    brain = build_brain_assisted_client_profile_prompt(TRANSCRIPT, context)
    diff = list(difflib.ndiff(baseline, brain.splitlines()))

    removed = [line[2:] for line in diff if line.startswith("- ")]
    added = [line[2:] for line in diff if line.startswith("+ ")]
    assert removed == [BASELINE_CONTEXT_RULE.rstrip("\n")]
    # Counter, not a list: difflib may match the inserted blank line at either end.
    assert Counter(added) == Counter(
        [
            BRAIN_CONTEXT_RULE.rstrip("\n"),
            "FA Systems context:",
            *context.splitlines(),
            "",
        ]
    )


def test_transcript_comes_after_the_context():
    prompt = build_brain_assisted_client_profile_prompt(TRANSCRIPT, "## Terms")
    assert prompt.index("FA Systems context:") < prompt.index("Transcript:")
    assert prompt.endswith(TRANSCRIPT + "\n")


def test_braces_in_context_or_transcript_are_kept_as_is():
    prompt = build_brain_assisted_client_profile_prompt("say {hi}", "use {curly}")
    assert "use {curly}" in prompt
    assert "say {hi}" in prompt


def test_fixture_context_renders_every_section():
    text = load_brain_context(BRAIN_FILE)
    assert text.startswith("## What FA Systems does\n- ")
    assert "## Onboarding playbook: capturing a client profile" in text
    assert "\n\n## Terms\n" in text


@pytest.mark.parametrize(
    "context",
    [
        [],
        {},
        {"sections": []},
        {"sections": ["not a dict"]},
        {"sections": [{"heading": "", "points": ["x"]}]},
        {"sections": [{"heading": "Terms", "points": "x"}]},
        {"sections": [{"heading": "Terms", "points": ["ok", ""]}]},
    ],
)
def test_invalid_context_is_rejected(context):
    with pytest.raises(ValueError):
        render_brain_context(context)


def test_prompts_cannot_drift_apart_if_the_baseline_wording_changes():
    """If someone rewords the baseline rule, importing the Brain prompt fails."""
    with (
        patch("src.ai.baseline_prompt.BASELINE_CLIENT_PROFILE_PROMPT", "Transcript:\n"),
        pytest.raises(RuntimeError, match="exactly once"),
    ):
        importlib.reload(brain_prompt)
    importlib.reload(brain_prompt)  # restore the real template for later tests
