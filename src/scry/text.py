"""Plain-text helpers shared by the report generators and the triage prompt."""

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?)])")


def plain_text(fragment: str) -> str:
    """Strip HTML tags, unescape entities, and collapse whitespace.

    Tags become spaces so block elements do not run together; the space that
    leaves before closing punctuation is removed again.
    """
    text = _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", fragment)))
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text).strip()


def summarize(text: str, limit: int = 400) -> str:
    """Trim text to `limit` characters, cutting at a sentence end when one is past the midpoint."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if end + 1 >= limit // 2:
        return cut[: end + 1]
    return cut.rstrip() + "..."
