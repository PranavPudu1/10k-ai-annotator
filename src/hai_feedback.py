"""Load and use the HAI (Naomi + Angie) feedback CSVs.

Each row is one HAI reviewer's verdict on one AI annotation, with a short
`explanation` label and a longer free-text rationale. We use this data
two ways:

1. Hand-distilled DON'T rules live in `data/hai_dont_rules.md` — those
   were written by reading samples of the explanations and noticing
   recurring failure modes (e.g. "Not specific to AI", "Not specific to
   RESPONSIBLE AI", duplicate annotations, sentence fragments).
2. Few-shot exemplars — `select_few_shot_examples` picks high-signal
   rows of both kinds (incorrect AI tags + human misses) to inject into
   the V4 prompt as worked examples.

Schema note: Naomi's CSV uses Decision / Explanation / Explanation
longer... columns. Angie's CSV uses Angie-Decision / Angie-Explanation /
Angie-Explanation longer... columns. The loader normalizes both into
one record shape.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path

from .config import ROOT


HAI_DIR = ROOT / "hai-annotations"
NAOMI_CSV = HAI_DIR / "Naomi-reasoning - 2024 ONLY.csv"
ANGIE_CSV = HAI_DIR / "Angie-reasoning - Rest of 2024.csv"


@dataclass(frozen=True)
class HAIRecord:
    reviewer: str          # "Naomi" | "Angie"
    doc_slug: str          # e.g. "alphabet_2024"
    source: str            # always "AI" in these files
    anchor_id: str         # e.g. "s-00273"
    sentence: str
    kind: str              # Risk | Risk Mitigation
    category: str
    subcategory: str
    strength: str
    decision: str          # "AI-flagged incorrectly" | "Human Miss" | ""
    explanation: str       # short label, often a recurring failure mode
    explanation_long: str  # verbatim free-text reasoning


def _normalize(row: dict) -> dict:
    return {
        "doc_slug": (row.get("10-K") or "").strip(),
        "source": (row.get("Source") or "").strip(),
        "anchor_id": (row.get("Anchor ID") or "").strip(),
        "sentence": (row.get("Sentence") or "").strip(),
        "kind": (row.get("Type") or "").strip(),
        "category": (row.get("Category") or "").strip(),
        "subcategory": (row.get("Subcategory") or "").strip(),
        "strength": (row.get("Strength") or "").strip(),
        "decision": (row.get("Decision") or row.get("Angie-Decision") or "").strip(),
        "explanation": (row.get("Explanation") or row.get("Angie-Explanation") or "").strip(),
        "explanation_long": (
            row.get("Explanation longer...")
            or row.get("Angie-Explanation longer...")
            or ""
        ).strip(),
    }


def load_hai_csvs() -> list[HAIRecord]:
    """Load both reviewer CSVs into a flat list of HAIRecord."""
    records: list[HAIRecord] = []
    for path, reviewer in [(NAOMI_CSV, "Naomi"), (ANGIE_CSV, "Angie")]:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                n = _normalize(row)
                if not n["anchor_id"] or not n["decision"]:
                    continue
                records.append(HAIRecord(reviewer=reviewer, **n))
    return records


def _dedupe_by_key(items: list[HAIRecord]) -> list[HAIRecord]:
    seen: set[tuple] = set()
    out: list[HAIRecord] = []
    for r in items:
        key = (r.doc_slug, r.anchor_id, r.kind, r.category, r.subcategory)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def select_few_shot_examples(
    records: list[HAIRecord], n_bad: int = 5, n_miss: int = 2
) -> list[HAIRecord]:
    """Pick n_bad 'AI-flagged incorrectly' + n_miss 'Human Miss' exemplars.

    Selection prefers rows whose `explanation_long` is meaty (>= 60 chars),
    spans diverse `explanation` short labels, and dedupes by anchor.
    """
    bad = _dedupe_by_key([r for r in records if r.decision == "AI-flagged incorrectly"])
    miss = _dedupe_by_key([r for r in records if r.decision == "Human Miss"])

    def pick(pool: list[HAIRecord], n: int) -> list[HAIRecord]:
        scored = [(len(r.explanation_long), r) for r in pool if len(r.explanation_long) >= 60]
        scored.sort(key=lambda t: -t[0])
        # Round-robin by short-label so we don't pick 5 of the same failure mode.
        out: list[HAIRecord] = []
        seen_labels: set[str] = set()
        for _, r in scored:
            if r.explanation in seen_labels:
                continue
            out.append(r)
            seen_labels.add(r.explanation)
            if len(out) >= n:
                break
        # Backfill from leftover scored if we didn't hit n.
        if len(out) < n:
            for _, r in scored:
                if r in out:
                    continue
                out.append(r)
                if len(out) >= n:
                    break
        return out[:n]

    return pick(bad, n_bad) + pick(miss, n_miss)


def format_examples_block(examples: list[HAIRecord]) -> str:
    """Render selected exemplars as a markdown block for the LLM prompt."""
    if not examples:
        return ""
    chunks: list[str] = []
    for r in examples:
        verdict = "WRONG" if r.decision == "AI-flagged incorrectly" else "HUMAN MISSED — model should have tagged"
        tag_line = f"Tagged as: {r.kind} / {r.category} / {r.subcategory}"
        if r.strength:
            tag_line += f" (strength {r.strength})"
        chunks.append(
            f"- Sentence: \"{r.sentence.strip()}\"\n"
            f"  {tag_line}\n"
            f"  Verdict: {verdict}\n"
            f"  Why: {r.explanation_long.strip()}"
        )
    return "\n\n".join(chunks)


if __name__ == "__main__":
    records = load_hai_csvs()
    print(f"{len(records)} HAI records loaded\n")
    examples = select_few_shot_examples(records)
    print(f"Selected {len(examples)} few-shot exemplars:\n")
    print(format_examples_block(examples))
