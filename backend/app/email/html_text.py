"""Turn an HTML email into readable plain text, using only the standard library."""

import re
from html.parser import HTMLParser

# Tags that start a new line in the rendered text.
_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"}
# Tags whose contents are never visible text.
_SKIP_TAGS = {"script", "style", "head", "title"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("  ")  # keep table cells (item / price) apart

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)
