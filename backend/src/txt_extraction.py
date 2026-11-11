"""Decode plain-text document bytes into normalized text."""

from src.text_decoding import decode_text
from src.text_normalization import normalize_text


def extract_txt(data: bytes) -> str:
    """Extract UTF-8 (with or without a BOM) or BOM-marked UTF-16 text.

    UTF-8 is the default when no BOM is present. Decode strictly so malformed
    bytes are rejected instead of silently replaced. Raises ValueError for
    unsupported UTF-32 BOMs, invalid encoding, NUL characters, or empty text.
    Keeps the file's last newline, since the model's draft can change without
    it (#156).
    """
    decoded = decode_text(data)
    text = normalize_text(decoded)
    if not text.strip():
        raise ValueError("Text is empty or contains only whitespace")
    return text + "\n" if decoded.endswith(("\n", "\r")) else text
