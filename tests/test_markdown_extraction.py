"""Checks for Markdown extraction that preserves readable document content."""

import codecs

import pytest

from src.markdown_extraction import extract_markdown


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        pytest.param(
            "# Onboarding\n\n**Alice:** We need *support*.",
            "Onboarding\n\nAlice: We need support.",
            id="headings-emphasis",
        ),
        pytest.param(
            "Title\n=====\n\n~~Old~~ **New**",
            "Title\n\nOld New",
            id="setext-strikethrough",
        ),
        pytest.param(
            "- First\n- Second\n\n1. Third\n2. Fourth",
            "First\nSecond\n\nThird\nFourth",
            id="lists",
        ),
        pytest.param(
            "- Parent\n  - Child\n- Next", "Parent\nChild\nNext", id="nested-list"
        ),
        pytest.param(
            "Read [launch support](https://example.com) and [brief][ref].\n\n[ref]: https://example.com/brief",
            "Read launch support and brief.",
            id="links",
        ),
        pytest.param("![Client **logo**](logo.png)", "Client logo", id="image-alt"),
        pytest.param(
            "Contact <team@example.com> &amp; enjoy &#233;.",
            "Contact team@example.com & enjoy é.",
            id="autolink-entities",
        ),
        pytest.param(
            "Use `**literal**` and `<tag>`.\n\n```txt\n  Alice: <client>\n**literal**\n```",
            "Use **literal** and <tag>.\n\n  Alice: <client>\n**literal**",
            id="code",
        ),
        pytest.param(
            "    Alice: **literal**\n    Bob: Hi.",
            "Alice: **literal**\nBob: Hi.",
            id="indented-code",
        ),
        pytest.param(
            "First line  \nSecond line\\\nThird line\nFourth line",
            "First line\nSecond line\nThird line\nFourth line",
            id="hard-and-soft-breaks",
        ),
        pytest.param(
            "> Alice: Hello.\n>\n> Bob: Hi.\n\n---\n\nNext paragraph.",
            "Alice: Hello.\n\nBob: Hi.\n\nNext paragraph.",
            id="blockquote-paragraphs",
        ),
        pytest.param(
            "| Speaker | Words |\n| --- | --- |\n| Alice | Hello |",
            "Speaker\tWords\nAlice\tHello",
            id="table",
        ),
        pytest.param(
            "<div><b>Alice:</b> Hello.<br>Bob: Hi.</div>",
            "Alice: Hello.\nBob: Hi.",
            id="html",
        ),
        pytest.param(
            "<section>Alice.</section><section>Bob.</section>",
            "Alice.\n\nBob.",
            id="html-sections",
        ),
        pytest.param(
            "Alice: one<br><br>Bob: two<hr>Next.",
            "Alice: one\n\nBob: two\n\nNext.",
            id="html-breaks",
        ),
        pytest.param(
            "\n# Cafe\u0301\r\n\r\n[00:01] **Alice:** Keep  two spaces.\t\r\n",
            "Café\n\n[00:01] Alice: Keep  two spaces.",
            id="normalization",
        ),
        pytest.param(
            "Unclosed **bold and [unfinished link",
            "Unclosed **bold and [unfinished link",
            id="unmatched-markers",
        ),
        pytest.param(
            r"\*literal\* and a_b_c", "*literal* and a_b_c", id="literal-punctuation"
        ),
        pytest.param(
            "<script>secret()</script>\n\n<style>p{color:red}</style>\n\nVisible.",
            "Visible.",
            id="non-readable-html",
        ),
    ],
)
def test_extracts_readable_markdown(markdown: str, expected: str):
    assert extract_markdown(markdown.encode()) == expected


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_decodes_bom_marked_markdown(encoding: str):
    assert extract_markdown("# Café 你好 👋".encode(encoding)) == "Café 你好 👋"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b" \t\r\n",
        b"#",
        b"---",
        b"<!-- hidden -->",
        b"[ref]: https://example.com",
        codecs.BOM_UTF8,
    ],
)
def test_rejects_markdown_without_readable_content(data: bytes):
    with pytest.raises(ValueError, match="empty or contains no readable text"):
        extract_markdown(data)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"\xff", "Invalid UTF-8"),
        (codecs.BOM_UTF16_LE + b"A", "Invalid UTF-8"),
        (codecs.BOM_UTF32_LE + b"A\x00\x00\x00", "UTF-32 is not supported"),
        (b"Alice\x00Bob", "NUL characters"),
    ],
)
def test_rejects_invalid_text_bytes(data: bytes, message: str):
    with pytest.raises(ValueError, match=message):
        extract_markdown(data)
