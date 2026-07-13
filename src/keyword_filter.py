"""Case-insensitive AI-vocabulary filter over the sentence index.

Loads a list of ~195 AI-related terms from a plain-text file (one per line)
and finds sentences that contain at least one of them as a substring.

A "hit" record:
    {
        "sentence_idx": int,        # position in sentences.json
        "anchor_id": str,           # e.g. "s-00486"
        "matched_terms": list[str], # original (non-lowercased) terms that hit
    }
"""
from __future__ import annotations
import json
import re
from pathlib import Path

from .config import DATA_DIR, paths_for


DEFAULT_KEYWORDS_PATH = DATA_DIR / "ai_keywords.txt"


def load_keywords(path: Path | str = DEFAULT_KEYWORDS_PATH) -> list[str]:
    raw = Path(path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in raw if line.strip()]


def _compile(keywords: list[str]) -> re.Pattern:
    """One alternation regex, case-insensitive, word-boundary-aware where useful.

    Word boundaries on multi-word phrases would over-restrict ("AI" should match
    "AI/ML"), so we just use case-insensitive substring. The 195-term list is
    curated so spurious matches on common English words are rare.
    """
    # Sort longest-first so "Artificial General Intelligence" wins over "AI"
    # when both could match a region — re.search returns the first match by
    # alternation order, not by length.
    sorted_keys = sorted(keywords, key=len, reverse=True)
    escaped = [re.escape(k) for k in sorted_keys]
    return re.compile("(" + "|".join(escaped) + ")", re.IGNORECASE)


def find_hits(sentences: list[dict], keywords: list[str]) -> list[dict]:
    """Return a list of hit records, one per sentence containing >=1 keyword."""
    pattern = _compile(keywords)
    hits: list[dict] = []
    for idx, sent in enumerate(sentences):
        matches = pattern.findall(sent["text"])
        if not matches:
            continue
        # Preserve order, dedupe (case-preserving — keep first form seen).
        seen: dict[str, None] = {}
        for m in matches:
            seen.setdefault(m, None)
        hits.append(
            {
                "sentence_idx": idx,
                "anchor_id": sent["anchor_id"],
                "matched_terms": list(seen),
            }
        )
    return hits


def write_hits_cache(slug: str, hits: list[dict]) -> Path:
    path = paths_for(slug)["out_dir"] / "keyword_hits.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hits, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_hits_cache(slug: str) -> list[dict] | None:
    path = paths_for(slug)["out_dir"] / "keyword_hits.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_or_compute_hits(slug: str, sentences: list[dict], keywords: list[str]) -> list[dict]:
    cached = read_hits_cache(slug)
    if cached is not None:
        return cached
    hits = find_hits(sentences, keywords)
    write_hits_cache(slug, hits)
    return hits
