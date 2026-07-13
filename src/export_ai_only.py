"""Export AI-only annotations (no human caught them) to a CSV folder.

"AI-only" = anchor_sources value of exactly "ai" — no Coder A, no Coder B.
Plus every entry in `unmatched_ai` (AI annotation we couldn't even align to
a sentence anchor, so by definition no human matched it either).

Output layout:
    dist/ai_only/
        all_ai_only.csv          # every doc concatenated
        {slug}_ai_only.csv       # one CSV per doc (flat)
    dist/ai_only.zip             # nested Company/Year.csv structure

Run: `python3 -m src.export_ai_only`
"""
from __future__ import annotations
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json as _json

from src.config import versioned_paths_for
from src.registry import discover_docs


_FIELDS = [
    "slug",
    "company",
    "year",
    "anchor_id",
    "sentence",
    "kind",
    "category",
    "subcategory",
    "strength",
]


def _rows_for_doc(doc, version_id: str = "baseline") -> list[dict]:
    v = versioned_paths_for(doc.slug, version_id)
    if not v["aligned_path"].exists():
        return []
    aligned = json.loads(v["aligned_path"].read_text(encoding="utf-8"))
    sentences = json.loads(doc.paths["sentences_path"].read_text(encoding="utf-8"))
    sentence_text = {s["anchor_id"]: s["text"] for s in sentences}

    rows: list[dict] = []
    anchor_sources = aligned.get("anchor_sources", {})
    cards_by_anchor = aligned.get("cards_by_anchor", {})

    # AI cards on anchors where ONLY AI tagged the sentence (no coder).
    for anchor_id, source in anchor_sources.items():
        if source != "ai":
            continue
        for card in cards_by_anchor.get(anchor_id, {}).get("ai", []):
            rows.append({
                "slug": doc.slug,
                "company": doc.company_display,
                "year": doc.year,
                "anchor_id": anchor_id,
                "sentence": sentence_text.get(anchor_id, ""),
                "kind": card.get("kind", ""),
                "category": card.get("category", ""),
                "subcategory": card.get("subcategory", ""),
                "strength": card.get("strength") if card.get("strength") is not None else "",
            })

    # Unmatched AI (couldn't align to any anchor — no human could match these either).
    for card in aligned.get("unmatched_ai", []) or []:
        rows.append({
            "slug": doc.slug,
            "company": doc.company_display,
            "year": doc.year,
            "anchor_id": "(unmatched)",
            "sentence": card.get("sentence_excerpt", ""),
            "kind": card.get("kind", ""),
            "category": card.get("category", ""),
            "subcategory": card.get("subcategory", ""),
            "strength": card.get("strength") if card.get("strength") is not None else "",
        })
    return rows


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def main(out_dir: Path | None = None, version_id: str = "baseline") -> Path:
    if out_dir is None:
        out_dir = _PROJECT_ROOT / "dist" / "ai_only"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir.parent / "ai_only.zip"

    all_rows: list[dict] = []
    per_doc: list[tuple[str, str, int, list[dict]]] = []  # (company, year, count, rows)
    for doc in discover_docs():
        if version_id not in doc.versions:
            continue
        rows = _rows_for_doc(doc, version_id=version_id)
        per_doc.append((doc.company_display, str(doc.year), len(rows), rows))
        # Flat per-doc CSV (matches the existing layout).
        per_doc_path = out_dir / f"{doc.slug}_ai_only.csv"
        per_doc_path.write_bytes(_csv_bytes(rows))
        all_rows.extend(rows)

    combined_path = out_dir / "all_ai_only.csv"
    combined_path.write_bytes(_csv_bytes(all_rows))

    # Zip with Company/Year.csv nested layout, plus an all_companies.csv at root.
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("all_companies.csv", _csv_bytes(all_rows))
        for company, year, _n, rows in per_doc:
            zf.writestr(f"{company}/{year}.csv", _csv_bytes(rows))

    print(f"Wrote {combined_path} ({len(all_rows)} rows across {len(per_doc)} docs)")
    print(f"Wrote {zip_path} (nested Company/Year.csv)")
    for company, year, n, _ in sorted(per_doc, key=lambda t: -t[2]):
        print(f"  {company} {year}: {n}")
    return out_dir


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--version", default="baseline", help="Strategy version to export (default: baseline).")
    args = p.parse_args()
    main(version_id=args.version)
