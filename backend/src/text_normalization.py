"""Normalize extracted document text before it is stored."""

import unicodedata


def normalize_text(text: str) -> str:
    """Use NFC Unicode and LF line endings while preserving transcript structure.

    Remove trailing spaces/tabs on each line and blank lines at the edges.
    Keep indentation, internal blank lines, speaker labels, and timestamps.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    return "\n".join(lines).strip("\n")
