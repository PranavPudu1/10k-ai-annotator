"""Extract plain text from the 10-K PDF using pdfplumber."""
from __future__ import annotations
import re
from pathlib import Path

import pdfplumber

from .config import PDF_PATH, TXT_PATH, ensure_output_dir


_URL_RE = re.compile(r"https?://\S+")
_LONE_DIGITS_RE = re.compile(r"^\s*\d+\s*$", re.MULTILINE)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_SINGLE_NEWLINE_INSIDE_PARA_RE = re.compile(r"(?<=[A-Za-z,;:\-])\n(?=[a-z\(])")


def _clean_page(text: str) -> str:
    text = _URL_RE.sub(" ", text)
    text = _LONE_DIGITS_RE.sub("", text)
    text = _SINGLE_NEWLINE_INSIDE_PARA_RE.sub(" ", text)
    return text


def extract_pdf(pdf_path: Path = PDF_PATH, out_path: Path = TXT_PATH, force: bool = False) -> str:
    ensure_output_dir()
    if out_path.exists() and not force and out_path.stat().st_mtime >= pdf_path.stat().st_mtime:
        return out_path.read_text(encoding="utf-8")

    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            pages.append(_clean_page(page_text))

    full = "\n\n".join(pages)
    full = _MULTI_NEWLINE_RE.sub("\n\n", full).strip()
    out_path.write_text(full, encoding="utf-8")
    return full


if __name__ == "__main__":
    text = extract_pdf(force=True)
    print(f"extracted {len(text):,} chars, {len(text.split()):,} words to {TXT_PATH}")
