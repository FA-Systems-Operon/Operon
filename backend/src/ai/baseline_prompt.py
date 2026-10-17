"""Baseline prompt for extracting a client profile from a raw transcript."""

BASELINE_CLIENT_PROFILE_PROMPT = """\
You are given a raw transcript of a conversation with a client.

Extract only information explicitly stated in the transcript.

Return a valid JSON object with exactly this structure:

{{
  "name": "string or null",
  "needs": ["string"],
  "goals": ["string"]
}}

Rules:
- name: the client's name, or null if it is not stated.
- needs: the client's stated needs, problems, or requirements.
- goals: the outcomes or objectives the client wants to achieve.
- If no needs or goals are stated, return an empty array for that field.
- Do not assume, infer, or invent information.
- Do not add business context or any information outside the transcript.
- Return only the JSON object. Do not use Markdown or explain your answer.

Transcript:
{transcript}
"""


def build_baseline_client_profile_prompt(transcript: str) -> str:
    """Insert a raw client transcript into the baseline prompt template."""
    return BASELINE_CLIENT_PROFILE_PROMPT.format(transcript=transcript)
