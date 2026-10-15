"""Decode plain-text document bytes into normalized text."""

import codecs

from src.text_normalization import normalize_text


def extract_txt(data: bytes) -> str:
    """Extract UTF-8 (with or without a BOM) or BOM-marked UTF-16 text.

    UTF-8 is the default when no BOM is present. Decode strictly so malformed
    bytes are rejected instead of silently replaced. Raises ValueError for
    unsupported UTF-32 BOMs, invalid encoding, NUL characters, or empty text.
    """
    # A UTF-32 LE BOM begins with the UTF-16 LE BOM, so check UTF-32 first.
    if data.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        raise ValueError("UTF-32 is not supported")

    encoding = (
        "utf-16"
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
        else "utf-8-sig"
    )
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError("Invalid UTF-8 or BOM-marked UTF-16 text") from exc

    # NUL characters cannot be stored in a PostgreSQL text column. They can
    # also indicate that BOM-less UTF-16 was incorrectly read as UTF-8.
    if "\x00" in text:
        raise ValueError("Text contains NUL characters")

    text = normalize_text(text)
    if not text.strip():
        raise ValueError("Text is empty or contains only whitespace")
    return text
