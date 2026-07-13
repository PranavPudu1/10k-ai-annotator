"""Parse the two-coder resolved-annotations spreadsheet.

The CSV is structured as:
  - Rows 1-N: title, "done" company list, process notes, legend (metadata).
  - Per-company sections, each:
      - One row with just the Company name in col 0 (everything else empty).
      - One header row starting with literal "Company,10-K Year,AI_Term,..."
      - Data rows until blank or next company-marker row.
  - Header columns:
      Company, 10-K Year, AI_Term,
      Coder A Name, Coder A: Sentences Highlighted, Coder A: Risk or Mitigation?,
      Coder A: Subcategory, Coder A: Strength Annotation,
      Coder B Name, Coder B: Sentences Highlighted, Coder B: Risk or Mitigation?,
      Coder B: Subcategory, Coder B: Strength Annotation,
      Descripancy Type, Explanation, Discussion 4/6

Output: DataFrame with one row PER CODER (so a single CSV row with both
coders filled becomes two output rows). Columns:
  company, company_display, company_slug, year, ai_term,
  coder ("A" | "B"), coder_name, sentence, kind, subcategory, strength,
  discrepancy_type, explanation
"""
from __future__ import annotations
import csv
from pathlib import Path

import pandas as pd


# Lazily import the slug map to avoid circular imports with registry.
def _slug_for(company: str) -> str | None:
    from .registry import canonical_slug

    return canonical_slug(company)


_HEADER_MARKER = "Company"  # first cell of the per-section header row
_KNOWN_HEADER_FIELDS = {
    "Coder A Name",
    "Coder A: Sentences Highlighted",
    "Coder A: Risk or Mitigation?",
    "Coder A: Subcategory",
    "Coder A: Strength Annotation",
    "Coder B Name",
    "Coder B: Sentences Highlighted",
    "Coder B: Risk or Mitigation?",
    "Coder B: Subcategory",
    "Coder B: Strength Annotation",
}


def _normalize_kind(raw: str) -> str:
    """The Alphabet test CSV uses 'Risk Mitigation', the new CSV uses 'Mitigation'.
    Normalize to the taxonomy spelling 'Risk Mitigation'."""
    v = (raw or "").strip()
    if not v:
        return ""
    low = v.lower()
    if low == "mitigation":
        return "Risk Mitigation"
    if low == "risk":
        return "Risk"
    if low == "risk mitigation":
        return "Risk Mitigation"
    return v


def _to_strength(raw) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, float) and pd.isna(raw):
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _is_section_marker(row: list[str]) -> str | None:
    """Return company display name if row is a bare company-name marker, else None."""
    if not row:
        return None
    first = (row[0] or "").strip()
    if not first:
        return None
    # Other cells must all be empty.
    if any((c or "").strip() for c in row[1:]):
        return None
    # Must be a known company.
    if _slug_for(first) is None:
        return None
    return first


def _is_header_row(row: list[str]) -> bool:
    if not row or (row[0] or "").strip() != _HEADER_MARKER:
        return False
    cells = {(c or "").strip() for c in row}
    return bool(_KNOWN_HEADER_FIELDS & cells)


def parse_two_coder_csv(path: str | Path) -> pd.DataFrame:
    """Parse the multi-section, two-coder CSV into a long-format DataFrame.

    Returns one row PER CODER per source row (so 0, 1, or 2 output rows per
    input data row depending on which coders filled in their highlights).
    """
    path = Path(path)
    records: list[dict] = []
    current_company: str | None = None
    current_slug: str | None = None
    header_idx: dict[str, int] | None = None

    with path.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        for raw_row in reader:
            row = list(raw_row)

            marker = _is_section_marker(row)
            if marker is not None:
                current_company = marker
                current_slug = _slug_for(marker)
                header_idx = None
                continue

            if _is_header_row(row):
                header_idx = {(c or "").strip(): i for i, c in enumerate(row)}
                continue

            if header_idx is None or current_company is None:
                continue  # still in pre-section metadata, or between sections

            def cell(name: str) -> str:
                i = header_idx.get(name)
                if i is None or i >= len(row):
                    return ""
                return (row[i] or "").strip()

            year_raw = cell("10-K Year")
            if not year_raw.isdigit():
                continue
            year = int(year_raw)

            ai_term = cell("AI_Term")
            discrepancy = cell("Descripancy Type")
            explanation = cell("Explanation")

            for coder_letter, name_col, sent_col, kind_col, sub_col, str_col in (
                (
                    "A",
                    "Coder A Name",
                    "Coder A: Sentences Highlighted",
                    "Coder A: Risk or Mitigation?",
                    "Coder A: Subcategory",
                    "Coder A: Strength Annotation",
                ),
                (
                    "B",
                    "Coder B Name",
                    "Coder B: Sentences Highlighted",
                    "Coder B: Risk or Mitigation?",
                    "Coder B: Subcategory",
                    "Coder B: Strength Annotation",
                ),
            ):
                sentence = cell(sent_col)
                if not sentence:
                    continue
                kind = _normalize_kind(cell(kind_col))
                subcategory = cell(sub_col)
                strength = _to_strength(cell(str_col))
                coder_name = cell(name_col)
                records.append(
                    {
                        "company": current_company,
                        "company_display": current_company,
                        "company_slug": current_slug,
                        "year": year,
                        "ai_term": ai_term,
                        "coder": coder_letter,
                        "coder_name": coder_name,
                        "sentence": sentence,
                        "kind": kind,
                        "subcategory": subcategory,
                        "strength": strength,
                        "discrepancy_type": discrepancy,
                        "explanation": explanation,
                    }
                )

    return pd.DataFrame(records)


def load_human_for_doc(slug: str, path: str | Path | None = None) -> pd.DataFrame:
    """Return the parsed CSV filtered to one (company_slug, year)."""
    if path is None:
        from .config import HUMAN_CSV_PATH

        path = HUMAN_CSV_PATH
    df = parse_two_coder_csv(path)
    company_slug, _, year_str = slug.rpartition("_")
    year = int(year_str)
    return df[(df["company_slug"] == company_slug) & (df["year"] == year)].reset_index(drop=True)


def coder_names_for_doc(human_df: pd.DataFrame) -> dict[str, str]:
    """Return {'A': 'Naomi', 'B': 'Chibudom'} for the most common name per coder slot."""
    out = {"A": "", "B": ""}
    for letter in ("A", "B"):
        names = human_df.loc[human_df["coder"] == letter, "coder_name"]
        names = [n for n in names.tolist() if n]
        if names:
            # Pick the most common; ties resolved by first occurrence.
            out[letter] = max(set(names), key=names.count)
    return out


if __name__ == "__main__":
    from .config import HUMAN_CSV_PATH

    df = parse_two_coder_csv(HUMAN_CSV_PATH)
    print(f"parsed {len(df)} per-coder records")
    print(df.groupby(["company_slug", "year", "coder"]).size().head(20))
