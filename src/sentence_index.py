"""Split the 10-K text into sentences using pysbd, assign anchor ids.

After pysbd, run a post-splitter merge pass that fixes two list-format
patterns pysbd handles awkwardly:

  Rule A: sentences ending with ':' are list-headers followed by bullets;
          merge into the following sentence.
  Rule B: sentences beginning with a lowercase letter when the previous
          sentence didn't end with a hard terminator ('.', '?', '!', '…')
          are mid-clause continuations; merge into the previous sentence.

Anchor IDs are re-assigned after merging so they stay contiguous.
"""
from __future__ import annotations
import json
from pathlib import Path

import pysbd

_HARD_TERMINATORS = (".", "?", "!", "…")


def _split_raw(text: str) -> list[dict]:
    """First-pass pysbd split, returning the same shape as before."""
    seg = pysbd.Segmenter(language="en", clean=False)
    out: list[dict] = []
    cursor = 0
    for raw in seg.segment(text):
        if not raw or not raw.strip():
            continue
        found = text.find(raw, cursor)
        if found == -1:
            stripped = raw.strip()
            found = text.find(stripped, cursor)
            if found == -1:
                continue
            char_start = found
            char_end = found + len(stripped)
        else:
            lead = len(raw) - len(raw.lstrip())
            trail = len(raw) - len(raw.rstrip())
            char_start = found + lead
            char_end = found + len(raw) - trail
        out.append({
            "text": text[char_start:char_end],
            "char_start": char_start,
            "char_end": char_end,
        })
        cursor = char_end
    return out


def _should_merge(prev: dict, curr: dict, source_text: str) -> bool:
    """Merge decision for the post-splitter pass.

    Rule A: previous ends with ':'.
    Rule B: current starts with a lowercase letter AND previous doesn't end
            with a hard terminator.
    """
    prev_text = prev["text"].rstrip()
    curr_text = curr["text"].lstrip()

    if not prev_text or not curr_text:
        return False

    # Rule A: previous ends with ':'.
    if prev_text.endswith(":"):
        return True

    # Rule B: current starts lowercase + previous not hard-terminated.
    if curr_text[0].isalpha() and curr_text[0].islower():
        if not prev_text.endswith(_HARD_TERMINATORS):
            return True

    return False


def _merge(prev: dict, curr: dict, source_text: str) -> dict:
    """Concatenate two adjacent sentences, spanning them in the source text."""
    return {
        "text": source_text[prev["char_start"]:curr["char_end"]],
        "char_start": prev["char_start"],
        "char_end": curr["char_end"],
    }


def _post_merge(raw_sentences: list[dict], source_text: str) -> list[dict]:
    """Apply merge rules until stable, then assign anchor IDs."""
    if not raw_sentences:
        return []
    merged: list[dict] = [raw_sentences[0]]
    for curr in raw_sentences[1:]:
        prev = merged[-1]
        if _should_merge(prev, curr, source_text):
            merged[-1] = _merge(prev, curr, source_text)
        else:
            merged.append(curr)
    # Assign anchor IDs after merging.
    for idx, s in enumerate(merged):
        s["anchor_id"] = f"s-{idx:05d}"
    # Re-order keys to match legacy output.
    return [
        {
            "anchor_id": s["anchor_id"],
            "text": s["text"],
            "char_start": s["char_start"],
            "char_end": s["char_end"],
        }
        for s in merged
    ]


def build_index(text: str) -> list[dict]:
    return _post_merge(_split_raw(text), text)


def write_index(sentences: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sentences, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Inline unit tests. Run with: python3 -m src.sentence_index
# ---------------------------------------------------------------------------
def _selftest() -> None:
    # Rule A: colon-terminated list header merges with the next sentence.
    text_a = "Responding to any such claim, regardless of its validity, could:\n• Cost significant time."
    a = build_index(text_a)
    assert len(a) == 1, f"Rule A failed: got {len(a)} sentences, expected 1"

    # Rule B: lowercase continuation merges into previous.
    text_b = (
        "prioritization of cybersecurity countermeasures and risk mitigation strategies\n"
        "support informed risk-based decision-making and prioritization"
    )
    b = build_index(text_b)
    assert len(b) == 1, f"Rule B failed: got {len(b)} sentences, expected 1"

    # Regression: SEGMENTER_DECISION.md style 10-K prose stays properly split.
    # Focus on the tricky bits (decimals, abbreviations, section numbers, Ph.D.).
    text_c = (
        "In fiscal year 2024, we invested approximately $7.4 billion in research and development, "
        "a 12.3% increase over fiscal year 2023. "
        "Regulatory bodies in the U.S. and the E.U. have introduced new artificial intelligence "
        "frameworks (e.g., the EU AI Act) that may impose significant compliance costs. "
        "Section 7.4.4 of our governance manual outlines our approach to model risk. "
        "Failure to attract qualified engineers, Ph.D. researchers, and other technical staff "
        "could harm our operations."
    )
    c = build_index(text_c)
    assert len(c) == 4, f"Regression failed: expected 4 sentences from clean 10-K prose, got {len(c)}"

    # Regression: colon inside a sentence (not at the end) does NOT merge.
    text_d = "Note: this is a full sentence with a colon inside. The next one is separate."
    d = build_index(text_d)
    assert len(d) == 2, f"Colon-mid-sentence merged incorrectly: {len(d)} sentences, expected 2"

    print("All splitter self-tests passed.")


if __name__ == "__main__":
    _selftest()
