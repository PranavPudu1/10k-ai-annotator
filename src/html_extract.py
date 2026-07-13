"""Extract plain prose from SEC 10-K HTML filings.

Replaces the old pdfplumber-based extractor. The fetched .htm files are
the full primary filing with embedded XBRL tags, navigation, and lots of
tabular financial data. For RAI annotation we only need the prose body,
so we strip:
  - <script>, <style>, comments, XBRL hidden blocks
  - <table> blocks (financial tables aren't where AI risk language lives)
  - hidden divs / aria-hidden / display:none / visibility:hidden
  - SEC navigation links / anchors / page-break wrappers
and keep paragraph boundaries from block-level elements.

Output: a single normalized text file at `output/{slug}/text.txt` that
the rest of the pipeline (sentence indexer, LLM, alignment) consumes
unchanged. Same shape as the old pdfplumber output.
"""
from __future__ import annotations
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment


_URL_RE = re.compile(r"https?://\S+")
_LONE_DIGITS_RE = re.compile(r"^\s*\d+\s*$", re.MULTILINE)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_SINGLE_NEWLINE_INSIDE_PARA_RE = re.compile(r"(?<=[A-Za-z,;:\-])\n(?=[a-z\(])")

# Block-level tags that should produce a paragraph break in the output.
_BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer", "main",
    "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "br",
    "tr",  # rows of any surviving tables get newlines
}

# Tags to drop entirely (subtree + content).
_DROP_TAGS = {
    "script", "style", "noscript", "head", "meta", "link", "title",
    "table",  # financial tables — noise for RAI annotation
    "img", "svg", "figure", "form", "button", "input", "select",
}

# Common XBRL/inline-XBRL tag prefixes whose content we keep but whose
# tag wrappers are not block-level.
_INLINE_TAGS = {"span", "a", "b", "i", "em", "strong", "u", "small", "font"}


def _is_hidden(tag) -> bool:
    if not getattr(tag, "attrs", None):
        return False
    style = (tag.attrs.get("style") or "").lower().replace(" ", "")
    if "display:none" in style or "visibility:hidden" in style:
        return True
    if tag.attrs.get("aria-hidden") == "true":
        return True
    if "hidden" in tag.attrs:
        return True
    return False


def _safe_decompose(tags) -> None:
    for t in list(tags):
        try:
            t.decompose()
        except Exception:
            pass


def _strip(soup: BeautifulSoup) -> None:
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for tag_name in _DROP_TAGS:
        _safe_decompose(soup.find_all(tag_name))
    # XBRL-namespaced hidden blocks (often appear as <ix:hidden>...).
    _safe_decompose(soup.find_all(lambda tag: tag.name and tag.name.lower().startswith("ix:hidden")))
    # Hidden elements via style/aria/hidden attributes.
    _safe_decompose([t for t in soup.find_all(True) if _is_hidden(t)])


def _walk(node, out: list[str]) -> None:
    """Recursively serialize block tags as newline-delimited paragraphs."""
    from bs4 import NavigableString

    for child in node.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text:
                out.append(text)
            continue
        name = (child.name or "").lower()
        if name in _DROP_TAGS:
            continue
        is_block = name in _BLOCK_TAGS
        if is_block:
            out.append("\n")
        _walk(child, out)
        if is_block:
            out.append("\n")


def _normalize(text: str) -> str:
    text = _URL_RE.sub(" ", text)
    text = text.replace(" ", " ")  # nbsp
    text = text.replace("​", "")   # zero-width space
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _LONE_DIGITS_RE.sub("", text)
    text = _SINGLE_NEWLINE_INSIDE_PARA_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    # Compact long runs of whitespace around newlines.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()


def extract_html(html_path: Path, out_path: Path, force: bool = False) -> str:
    """Extract prose from a single 10-K HTML filing.

    Caches the normalized text at `out_path` and returns it. If the cached
    text is newer than the source HTML and `force` is False, returns the cache.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        out_path.exists()
        and not force
        and out_path.stat().st_mtime >= html_path.stat().st_mtime
    ):
        return out_path.read_text(encoding="utf-8")

    raw = html_path.read_bytes()
    soup = BeautifulSoup(raw, "lxml")
    _strip(soup)

    body = soup.body or soup
    chunks: list[str] = []
    _walk(body, chunks)
    text = "".join(chunks)
    text = _normalize(text)

    out_path.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    import sys
    from .config import paths_for

    slug = sys.argv[1] if len(sys.argv) > 1 else "apple_2024"
    p = paths_for(slug)
    text = extract_html(p["html_path"], p["txt_path"], force=True)
    print(f"extracted {len(text):,} chars, {len(text.split()):,} words to {p['txt_path']}")
