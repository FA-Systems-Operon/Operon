"""Brain-assisted prompt for US 2.2: the baseline prompt plus FA Systems context.

Built from the baseline template so the two prompts differ only in the context
section and the one rule that forbade business context (see #28).
"""

import json
from pathlib import Path

from src.ai.baseline_prompt import BASELINE_CLIENT_PROFILE_PROMPT

BASELINE_CONTEXT_RULE = (
    "- Do not add business context or information outside the transcript.\n"
)
BRAIN_CONTEXT_RULE = (
    "- Use the FA Systems context only to understand the transcript. Never copy"
    " details from the context into the profile; every value must come from the"
    " transcript.\n"
)
TRANSCRIPT_HEADING = "Transcript:\n"


def _build_template() -> str:
    # Fail at import if the baseline wording changes, so the prompts can't drift apart.
    for text in (BASELINE_CONTEXT_RULE, TRANSCRIPT_HEADING):
        if BASELINE_CLIENT_PROFILE_PROMPT.count(text) != 1:
            raise RuntimeError(f"Baseline prompt must contain {text!r} exactly once")
    return BASELINE_CLIENT_PROFILE_PROMPT.replace(
        BASELINE_CONTEXT_RULE, BRAIN_CONTEXT_RULE
    ).replace(
        TRANSCRIPT_HEADING,
        "FA Systems context:\n{brain_context}\n\n" + TRANSCRIPT_HEADING,
    )


BRAIN_ASSISTED_CLIENT_PROFILE_PROMPT = _build_template()


def render_brain_context(context: dict) -> str:
    """Turn Brain context ({"sections": [{"heading", "points"}]}) into prompt text."""
    sections = context.get("sections") if isinstance(context, dict) else None
    if not isinstance(sections, list) or not sections:
        raise ValueError("Brain context needs a non-empty 'sections' list")

    blocks = []
    for section in sections:
        heading = section.get("heading") if isinstance(section, dict) else None
        points = section.get("points") if isinstance(section, dict) else None
        if not isinstance(heading, str) or not heading:
            raise ValueError("Each Brain context section needs a 'heading' string")
        if not isinstance(points, list) or not all(
            isinstance(point, str) and point for point in points
        ):
            raise ValueError(f"Section {heading!r} needs a list of 'points' strings")
        blocks.append("\n".join([f"## {heading}", *(f"- {p}" for p in points)]))
    return "\n\n".join(blocks)


def load_brain_context(path: Path) -> str:
    """Read a Brain context JSON file and render it as prompt text."""
    return render_brain_context(json.loads(Path(path).read_text(encoding="utf-8")))


def build_brain_assisted_client_profile_prompt(
    transcript: str, brain_context: str
) -> str:
    """Insert rendered Brain context and a raw transcript into the prompt."""
    return BRAIN_ASSISTED_CLIENT_PROFILE_PROMPT.format(
        brain_context=brain_context, transcript=transcript
    )
