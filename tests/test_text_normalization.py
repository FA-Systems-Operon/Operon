"""Checks for consistent text without changing transcript content."""

import pytest

from src.text_normalization import normalize_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("", "", id="empty"),
        pytest.param(" \t\r\n\t\r", "", id="blank-only"),
        pytest.param("Alice: Hello.", "Alice: Hello.", id="already-normalized"),
        pytest.param(
            "Alice\r\nBob\rCharlie\nDana",
            "Alice\nBob\nCharlie\nDana",
            id="line-endings",
        ),
        pytest.param("Alice  \t\nBob\t ", "Alice\nBob", id="trailing-whitespace"),
        pytest.param("\n \t\nAlice\n\t\n", "Alice", id="edge-blank-lines"),
        pytest.param("Alice\n \t\n\nBob", "Alice\n\n\nBob", id="internal-blank-lines"),
        pytest.param(
            "  Alice: Hello.\n\tBob: Hi.",
            "  Alice: Hello.\n\tBob: Hi.",
            id="indentation",
        ),
        pytest.param("Cafe\u0301", "Caf\u00e9", id="unicode-nfc"),
        pytest.param("Ａlice: 你好 👋", "Ａlice: 你好 👋", id="unicode-content"),
    ],
)
def test_normalize_text(text: str, expected: str):
    assert normalize_text(text) == expected


def test_preserves_transcript_content():
    text = (
        "\r\n[00:01] Alice: Launch is 2026-11-10.  \r\n"
        "\r\n[00:02] Bob: Budget is $1,000; keep  two spaces.\t\r\n"
    )

    assert normalize_text(text) == (
        "[00:01] Alice: Launch is 2026-11-10.\n"
        "\n[00:02] Bob: Budget is $1,000; keep  two spaces."
    )


@pytest.mark.parametrize(
    "text",
    ["", " \t\r\n", "Cafe\u0301\r\n\r\n  Bob: Hi.  \t\r", "Alice: Hello."],
)
def test_normalization_is_idempotent(text: str):
    normalized = normalize_text(text)

    assert normalize_text(normalized) == normalized
