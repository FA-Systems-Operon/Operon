"""Synthetic document samples shared by Brain tests; no application imports."""

from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def make_pdf(pages: list[str | None], *, password: str | None = None) -> bytes:
    """Build real PDF bytes with a standard font and one line per text item."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text is None:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        commands = [b"BT /F1 12 Tf 16 TL 72 720 Td"]
        for line in text.split("\n"):
            escaped = (
                line.encode("cp1252")
                .replace(b"\\", b"\\\\")
                .replace(b"(", b"\\(")
                .replace(b")", b"\\)")
            )
            commands.append(b"(" + escaped + b") Tj T*")
        commands.append(b"ET")
        content = DecodedStreamObject()
        content.set_data(b"\n".join(commands))
        page[NameObject("/Contents")] = writer._add_object(content)
    if password is not None:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def invalid_upload_samples():
    """Filename, bytes, MIME type, and expected status for rejected uploads."""
    return [
        ("brief.docx", b"hello", "text/plain", 415),
        ("brief", b"hello", "application/octet-stream", 415),
        ("brief.txt", b"\xff", "text/plain", 422),
        ("brief.txt", b" \t\n", "text/plain", 422),
        ("brief.md", b"---", "text/markdown", 422),
        ("brief.pdf", b"not a PDF", "application/pdf", 422),
        ("brief.pdf", make_pdf([None]), "application/pdf", 422),
        ("brief.pdf", make_pdf(["hello"], password="secret"), "application/pdf", 422),
    ]
