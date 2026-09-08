#!/usr/bin/env python3
"""Split the full annotations export into per-company / per-year CSVs + an index.

Pure post-processing on a local CSV file — this NEVER touches the annotation
tool or its database. It reads tool-exports/annotations.csv and writes:

  tool-exports/by-company/<Company>/<Company>_<Year>.csv   (one filing's rows)
  tool-exports/by-company/README.md                        (clickable index)

The by-company/ tree is rebuilt from scratch each run so companies/years that
disappear upstream don't leave stale files behind.

Usage:  python3 scripts/split_by_company.py
"""
import csv
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "tool-exports", "annotations.csv")
OUT = os.path.join(ROOT, "tool-exports", "by-company")

# CSV fields can be huge (full sentence / context text); lift the field limit.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def slug(s: str) -> str:
    """Filesystem/URL-friendly token: strip path-unsafe chars, spaces -> _."""
    s = (s or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)   # path-unsafe
    s = re.sub(r"\s+", "_", s)             # spaces -> _
    s = s.strip("._-")
    return s or "unknown"


def main() -> int:
    if not os.path.exists(SRC):
        print(f"::error::{SRC} not found", file=sys.stderr)
        return 1

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)

    with open(SRC, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Column positions in the tool's export: cik, company, year, accession, ...
        c_company = header.index("company")
        c_year = header.index("year")

        # (company, year) -> list of rows
        groups: dict[tuple[str, str], list[list[str]]] = {}
        for row in reader:
            if not row:
                continue
            key = (row[c_company], row[c_year])
            groups.setdefault(key, []).append(row)

    # Write one CSV per (company, year), grouped into a folder per company.
    # by_company_display: original company name -> {year -> relative path}
    index: dict[str, dict[str, str]] = {}
    for (company, year), rows in groups.items():
        comp_dir = slug(company)
        fname = f"{comp_dir}_{slug(year)}.csv"
        rel = f"{comp_dir}/{fname}"
        abs_dir = os.path.join(OUT, comp_dir)
        os.makedirs(abs_dir, exist_ok=True)
        with open(os.path.join(abs_dir, fname), "w", newline="", encoding="utf-8") as out:
            w = csv.writer(out)
            w.writerow(header)
            w.writerows(rows)
        index.setdefault(company, {})[year] = rel

    # Build the clickable index (README.md renders when the folder is opened).
    lines = [
        "# Annotations by company",
        "",
        "Auto-generated — do not edit by hand. Pick a company, then a year, to open",
        "just that filing's annotations (GitHub shows each CSV as a searchable table;",
        'use the "Download raw file" button to save it). For every filing in one file,',
        "see [`../annotations.csv`](../annotations.csv).",
        "",
        f"**{len(index)} companies · {len(groups)} company-years**",
        "",
    ]
    for company in sorted(index, key=lambda s: s.lower()):
        years = index[company]
        year_links = " · ".join(
            f"[{y}]({years[y]})" for y in sorted(years, key=lambda x: str(x))
        )
        lines.append(f"- **{company}** — {year_links}")
    lines.append("")

    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as idx:
        idx.write("\n".join(lines))

    print(f"Split into {len(groups)} company-year CSVs across {len(index)} companies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
