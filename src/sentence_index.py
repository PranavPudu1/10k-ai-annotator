"""Split the 10-K text into sentences using pysbd, assign anchor ids."""
from __future__ import annotations
import json
from pathlib import Path

import pysbd


def build_index(text: str) -> list[dict]:
    seg = pysbd.Segmenter(language="en", clean=False)
    sentences: list[dict] = []
    cursor = 0
    idx = 0
    for raw in seg.segment(text):
        if not raw or not raw.strip():
            continue
        # Locate this segment in the original text, starting from cursor so we
        # preserve document order and don't match a later identical occurrence.
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
        sentences.append({
            "anchor_id": f"s-{idx:05d}",
            "text": text[char_start:char_end],
            "char_start": char_start,
            "char_end": char_end,
        })
        cursor = char_end
        idx += 1
    return sentences


def write_index(sentences: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sentences, ensure_ascii=False, indent=2), encoding="utf-8")
