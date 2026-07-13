"""Single source of truth for the universe of (Company, Year) 10-Ks.

The registry walks `data/10ks/*.htm` so the doc set matches whatever the
EDGAR fetcher (`data/fetch_10ks.py`) downloaded. The human-annotations
CSV is consulted per-doc to attach has_human / coder names.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .config import DOCS_DIR, HUMAN_CSV_PATH, OUTPUT_DIR, paths_for

# CSV display name -> slug company part. "Facebook" and "Facebook/Meta"
# both map to "meta" because the EDGAR fetch in data/fetch_10ks.py
# saves the filings as meta_*.htm.
CANONICAL_COMPANY: dict[str, str] = {
    "alphabet": "alphabet",
    "amazon": "amazon",
    "apple": "apple",
    "broadcom": "broadcom",
    "facebook": "meta",
    "facebook/meta": "meta",
    "meta": "meta",
    "microsoft": "microsoft",
    "nvidia": "nvidia",
    "netflix": "netflix",
    "oracle": "oracle",
    "tesla": "tesla",
}

# Inverse: slug company part -> display name shown in the dropdown.
DISPLAY_BY_SLUG: dict[str, str] = {
    "alphabet": "Alphabet",
    "amazon": "Amazon",
    "apple": "Apple",
    "broadcom": "Broadcom",
    "meta": "Meta",
    "microsoft": "Microsoft",
    "nvidia": "NVIDIA",
    "netflix": "Netflix",
    "oracle": "Oracle",
    "tesla": "Tesla",
}

def canonical_slug(company: str) -> str | None:
    """Map a CSV `Company` cell to its slug company part. Returns None for unknowns."""
    key = (company or "").strip().lower()
    return CANONICAL_COMPANY.get(key)


def _split_slug(slug: str) -> tuple[str, int] | None:
    company_slug, _, year_str = slug.rpartition("_")
    if not company_slug or not year_str.isdigit():
        return None
    return company_slug, int(year_str)


@dataclass(frozen=True)
class Doc:
    slug: str
    company_display: str
    company_slug: str
    year: int
    html_path: Path
    paths: dict
    has_html: bool
    has_ai: bool
    has_human: bool
    versions: tuple[str, ...] = ()  # version ids with a built aligned.json


def _human_pairs(human_csv_path: Path) -> set[tuple[str, int]]:
    """Return the set of (company_slug, year) pairs present in the human CSV
    with at least one highlighted sentence."""
    from .multi_human_csv import parse_two_coder_csv

    df = parse_two_coder_csv(human_csv_path)
    if df.empty:
        return set()
    return {(row["company_slug"], int(row["year"])) for _, row in df.iterrows()}


def available_versions(slug: str) -> list[str]:
    """Return version_ids that have an aligned.json under output/{slug}/versions/."""
    versions_dir = OUTPUT_DIR / slug / "versions"
    if not versions_dir.exists():
        return []
    out: list[str] = []
    for child in sorted(versions_dir.iterdir()):
        if child.is_dir() and (child / "aligned.json").exists():
            out.append(child.name)
    return out


def discover_docs(human_csv_path: Path = HUMAN_CSV_PATH) -> list[Doc]:
    """Walk data/10ks/*.htm and return a Doc per file. has_human is True if
    the CSV has at least one annotation row for that (company, year)."""
    docs: list[Doc] = []
    human_pairs = _human_pairs(human_csv_path) if human_csv_path.exists() else set()

    if not DOCS_DIR.exists():
        return docs

    for html_path in sorted(DOCS_DIR.glob("*.htm")):
        slug = html_path.stem
        split = _split_slug(slug)
        if split is None:
            continue
        company_slug, year = split
        if company_slug not in DISPLAY_BY_SLUG:
            continue
        paths = paths_for(slug)
        versions = tuple(available_versions(slug))
        docs.append(
            Doc(
                slug=slug,
                company_display=DISPLAY_BY_SLUG[company_slug],
                company_slug=company_slug,
                year=year,
                html_path=html_path,
                paths=paths,
                has_html=True,
                has_ai=bool(versions),
                has_human=(company_slug, year) in human_pairs,
                versions=versions,
            )
        )
    return docs


def get_doc(slug: str, docs: list[Doc] | None = None) -> Doc | None:
    if docs is None:
        docs = discover_docs()
    for d in docs:
        if d.slug == slug:
            return d
    return None


if __name__ == "__main__":
    docs = discover_docs()
    print(f"{len(docs)} docs in registry")
    for d in docs:
        flags = []
        flags.append("html" if d.has_html else "no-html")
        flags.append("human" if d.has_human else "no-human")
        v = ",".join(d.versions) if d.versions else "no-versions"
        print(f"  {d.slug:<22} {d.company_display:<10} {d.year}  [{', '.join(flags)}]  versions=[{v}]")
