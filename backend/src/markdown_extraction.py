"""Extract readable plain text from Markdown documents."""

from html.parser import HTMLParser

from markdown_it import MarkdownIt

from src.text_decoding import decode_text
from src.text_normalization import normalize_text


class _PlainTextParser(HTMLParser):
    """Read Markdown's rendered HTML as text, preserving block boundaries."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.in_pre = False
        self.list_depth = 0
        self.after_br = False
        self.ignored_tag: str | None = None

    def _break(self, count: int) -> None:
        if self.parts:
            last = self.parts[-1]
            existing = len(last) - len(last.rstrip("\n"))
            self.parts[-1] += "\n" * max(0, count - existing)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.ignored_tag = tag
        elif tag in {"ul", "ol"}:
            self.list_depth += 1
        elif tag == "pre":
            self.in_pre = True
        elif tag == "br":
            self.parts.append("\n")
            self.after_br = True
        elif tag == "hr":
            self._break(2)
        elif tag == "img":
            self.parts.append(dict(attrs).get("alt") or "")

    def handle_endtag(self, tag: str) -> None:
        if self.ignored_tag is not None:
            if tag == self.ignored_tag:
                self.ignored_tag = None
            return
        if tag == "pre":
            self.in_pre = False
        if tag in {"ul", "ol"}:
            self.list_depth -= 1
            self._break(1 if self.list_depth else 2)
            return
        if tag in {
            "p",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "pre",
            "div",
            "section",
            "article",
            "header",
            "footer",
            "aside",
            "main",
            "nav",
            "address",
            "figure",
            "figcaption",
            "details",
            "summary",
            "dl",
            "dt",
            "dd",
            "blockquote",
            "table",
        }:
            self._break(2)
        elif tag in {"li", "tr"}:
            self._break(1)
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_data(self, data: str) -> None:
        if self.after_br:
            data = data.removeprefix("\n")
            self.after_br = False
        # Ignore whitespace inserted between HTML blocks by the renderer, while
        # keeping inline spaces and whitespace inside code blocks.
        if self.ignored_tag is None and (
            self.in_pre or not (data.isspace() and "\n" in data)
        ):
            self.parts.append(data)


def extract_markdown(data: bytes) -> str:
    """Decode and strip Markdown/HTML markup, then normalize the readable text.

    Preserve link labels, image alt text, code, paragraph breaks, and list/table
    boundaries. Script/style bodies and comments have no readable content.
    Unmatched Markdown markers are treated as literal text by the parser.
    Raises ValueError for decoding errors or documents without readable text.
    """
    markdown = decode_text(data)
    html = MarkdownIt("commonmark").enable(["table", "strikethrough"]).render(markdown)
    parser = _PlainTextParser()
    parser.feed(html)
    parser.close()
    text = normalize_text("".join(parser.parts))
    if not text.strip():
        raise ValueError("Markdown is empty or contains no readable text")
    return text
