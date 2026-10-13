"""Decode text document bytes without changing whitespace or markup."""

import codecs


def decode_text(data: bytes) -> str:
    """Decode UTF-8 or BOM-marked UTF-16 strictly, rejecting UTF-32 and NULs."""
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

    # PostgreSQL text columns cannot store NUL characters.
    if "\x00" in text:
        raise ValueError("Text contains NUL characters")
    return text
