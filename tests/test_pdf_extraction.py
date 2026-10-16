"""Checks using synthetic PDFs for text extraction, exclusion, and failures."""

from io import BytesIO

import pytest
from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.errors import DependencyError
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)
from tests.sample_data import make_pdf

from src.pdf_extraction import MAX_PDF_PAGES, extract_pdf


def test_extracts_normalized_transcript():
    data = make_pdf(["Alice: Café.  \nBob: Keep  two spaces.\t"])

    assert extract_pdf(data) == "Alice: Café.\nBob: Keep  two spaces."


def test_preserves_page_order_and_skips_blank_pages():
    data = make_pdf(
        [None, "[00:01] Alice: First page.", None, "[00:02] Bob: Second page.", None]
    )

    assert extract_pdf(data) == (
        "[00:01] Alice: First page.\n\n[00:02] Bob: Second page."
    )


def test_extracts_pdf_at_page_limit():
    pages = [f"Page {number}" for number in range(1, MAX_PDF_PAGES + 1)]

    assert extract_pdf(make_pdf(pages)) == "\n\n".join(pages)


@pytest.mark.parametrize("extra_page", [None, "Over the limit"])
def test_rejects_pdf_over_page_limit_before_extracting_text(monkeypatch, extra_page):
    data = make_pdf(["Readable page"] * MAX_PDF_PAGES + [extra_page])

    def unexpected_extraction(*args, **kwargs):
        pytest.fail("Oversized PDFs must be rejected before extracting any text")

    monkeypatch.setattr(PageObject, "extract_text", unexpected_extraction)

    with pytest.raises(
        ValueError, match=f"^PDF exceeds the maximum of {MAX_PDF_PAGES} pages$"
    ):
        extract_pdf(data)


def test_rejects_malformed_page_tree():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer._pages.get_object()[NameObject("/Kids")] = NumberObject(1)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ValueError, match="malformed or unsupported content"):
        extract_pdf(output.getvalue())


@pytest.mark.parametrize("pages", [[], [None], [" \t"], [None, None]])
def test_rejects_pdf_without_readable_text(pages: list[str | None]):
    with pytest.raises(ValueError, match="no readable text; OCR is not supported"):
        extract_pdf(make_pdf(pages))


def test_rejects_image_only_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    image = DecodedStreamObject()
    image.set_data(b"\xff\xff\xff")
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Im1"): writer._add_object(image)}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(b"q 100 0 0 100 72 600 cm /Im1 Do Q")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ValueError, match="no readable text; OCR is not supported"):
        extract_pdf(output.getvalue())


@pytest.mark.parametrize("password", ["secret", ""])
def test_rejects_encrypted_pdf(password: str):
    with pytest.raises(ValueError, match="Encrypted PDFs are not supported"):
        extract_pdf(make_pdf(["Alice: Hello."], password=password))


@pytest.mark.parametrize("data", [b"", b"not a PDF", b"%PDF-1.7\n%%EOF"])
def test_rejects_invalid_pdf(data: bytes):
    with pytest.raises(ValueError, match="invalid or malformed"):
        extract_pdf(data)


def test_rejects_truncated_pdf():
    data = make_pdf(["Alice: Hello."])
    truncated = data.split(b"startxref")[0]

    with pytest.raises(ValueError, match="invalid or malformed"):
        extract_pdf(truncated)


def test_rejects_malformed_page_content():
    reader = PdfReader(BytesIO(make_pdf(["Alice: Hello."])))
    writer = PdfWriter()
    page = writer.add_page(reader.pages[0])
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf (unterminated")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ValueError, match="malformed or unsupported content"):
        extract_pdf(output.getvalue())


def test_rejects_nul_characters():
    with pytest.raises(ValueError, match="NUL characters"):
        extract_pdf(make_pdf(["Alice\x00Bob"]))


def test_translates_missing_encryption_dependency(monkeypatch):
    def reader_without_crypto(*args, **kwargs):
        raise DependencyError("Cryptography dependency required")

    monkeypatch.setattr("src.pdf_extraction.PdfReader", reader_without_crypto)

    with pytest.raises(ValueError, match="Encrypted PDFs are not supported"):
        extract_pdf(b"encrypted PDF")
