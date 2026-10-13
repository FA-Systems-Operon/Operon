"""Checks for decoding TXT documents without losing transcript content."""

import codecs

import pytest

from src.txt_extraction import extract_txt


@pytest.mark.parametrize(
    "data",
    [
        pytest.param("Alice: Café — 你好 👋".encode(), id="utf-8"),
        pytest.param("Alice: Café — 你好 👋".encode("utf-8-sig"), id="utf-8-bom"),
        pytest.param(
            codecs.BOM_UTF16_LE + "Alice: Café — 你好 👋".encode("utf-16-le"),
            id="utf-16-le-bom",
        ),
        pytest.param(
            codecs.BOM_UTF16_BE + "Alice: Café — 你好 👋".encode("utf-16-be"),
            id="utf-16-be-bom",
        ),
    ],
)
def test_decodes_supported_encodings(data: bytes):
    assert extract_txt(data) == "Alice: Café — 你好 👋"


def test_extracts_normalized_transcript():
    data = (
        "\r\n[00:01] Alice: Cafe\u0301.  \r\n\r\n  [00:02] Bob: Keep  two spaces.\t\r\n"
    ).encode("utf-8-sig")

    assert extract_txt(data) == (
        "[00:01] Alice: Café.\n\n  [00:02] Bob: Keep  two spaces."
    )


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b" \t\r\n", id="whitespace-only"),
        pytest.param("\u00a0".encode("utf-8"), id="unicode-whitespace-only"),
        pytest.param(codecs.BOM_UTF8, id="utf-8-bom-only"),
        pytest.param(codecs.BOM_UTF16_LE, id="utf-16-le-bom-only"),
        pytest.param(codecs.BOM_UTF16_BE, id="utf-16-be-bom-only"),
    ],
)
def test_rejects_empty_text(data: bytes):
    with pytest.raises(ValueError, match="empty or contains only whitespace"):
        extract_txt(data)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"Caf\xe9", id="unsupported-legacy-encoding"),
        pytest.param(b"\xe2\x82", id="truncated-utf-8"),
        pytest.param(codecs.BOM_UTF16_LE + b"A", id="truncated-utf-16-le"),
        pytest.param(codecs.BOM_UTF16_BE + b"\x00", id="truncated-utf-16-be"),
        pytest.param(codecs.BOM_UTF16_LE + b"\x00\xd8", id="utf-16-le-surrogate"),
        pytest.param(codecs.BOM_UTF16_BE + b"\xd8\x00", id="utf-16-be-surrogate"),
    ],
)
def test_rejects_invalid_encoding(data: bytes):
    with pytest.raises(ValueError, match="Invalid UTF-8 or BOM-marked UTF-16"):
        extract_txt(data)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"Alice\x00Bob", id="utf-8-nul"),
        pytest.param("Alice".encode("utf-16-le"), id="utf-16-le-without-bom"),
        pytest.param("Alice".encode("utf-16-be"), id="utf-16-be-without-bom"),
    ],
)
def test_rejects_nul_characters(data: bytes):
    with pytest.raises(ValueError, match="NUL characters"):
        extract_txt(data)


@pytest.mark.parametrize("encoding", ["utf-32-le", "utf-32-be"])
def test_rejects_utf_32(encoding: str):
    bom = codecs.BOM_UTF32_LE if encoding == "utf-32-le" else codecs.BOM_UTF32_BE
    data = bom + "Alice: Hello.".encode(encoding)

    with pytest.raises(ValueError, match="UTF-32 is not supported"):
        extract_txt(data)
