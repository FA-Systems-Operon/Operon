"""Extract normalized text from unencrypted, text-based PDFs without OCR."""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import DependencyError, PyPdfError

from src.text_normalization import normalize_text


def extract_pdf(data: bytes) -> str:
    """Read embedded text in page order, with a blank line between readable pages.

    Skip pages without text. Reject encrypted PDFs, malformed or unsupported
    content, NUL characters, and PDFs without readable text. Raises ValueError.
    Image-only pages are not transcribed; this function does not perform OCR.
    """
    try:
        reader = PdfReader(BytesIO(data), strict=True)
    except DependencyError as exc:
        # Opening some encrypted PDFs requires an optional crypto dependency.
        raise ValueError("Encrypted PDFs are not supported") from exc
    except (PyPdfError, ValueError, TypeError, KeyError, IndexError) as exc:
        raise ValueError("PDF is invalid or malformed") from exc

    try:
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported")

        pages: list[str] = []
        try:
            for page in reader.pages:
                text = normalize_text(page.extract_text() or "")
                if text.strip():
                    pages.append(text)
        except (
            PyPdfError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            NotImplementedError,
        ) as exc:
            raise ValueError("PDF contains malformed or unsupported content") from exc

        text = "\n\n".join(pages)
        if "\x00" in text:
            raise ValueError("Text contains NUL characters")
        if not text.strip():
            raise ValueError("PDF contains no readable text; OCR is not supported")
        return text
    finally:
        reader.close()
