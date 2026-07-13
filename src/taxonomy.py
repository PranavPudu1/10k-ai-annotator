"""Load the taxonomy, strength rubric, and assumptions for the LLM prompt.

The multi-doc human-annotation CSV is loaded by `src/multi_human_csv.py`;
this module stays focused on the taxonomy that feeds the LLM.
"""
from __future__ import annotations
import glob
from pathlib import Path
from collections import defaultdict

import pandas as pd

from .config import DATA_DIR

KIND_RISK = "Risk"
KIND_MITIGATION = "Risk Mitigation"


def _find(pattern: str) -> Path:
    matches = glob.glob(str(DATA_DIR / pattern))
    if not matches:
        raise FileNotFoundError(f"No data file matching {pattern} in {DATA_DIR}")
    return Path(matches[0])


def _clean(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().rstrip(";").rstrip().strip()


def load_taxonomy() -> dict:
    """Returns the taxonomy dict.

    `subcat_to_cat[(kind, subcategory_lower)]` is a *list* of possible categories.
    "Other" under Risk maps to 4 categories — the human CSV disambiguates with a
    `"Legal; Other"` prefix format (see `resolve_category`).
    """
    tax_df = pd.read_csv(_find("*taxonomy*.csv"))
    kind_col, cat_col, sub_col, desc_col = tax_df.columns[0], tax_df.columns[1], tax_df.columns[2], tax_df.columns[3]

    risks: list[dict] = []
    mitigations: list[dict] = []
    subcat_to_cat: dict[tuple[str, str], list[str]] = defaultdict(list)

    for _, row in tax_df.iterrows():
        kind = _clean(row[kind_col])
        category = _clean(row[cat_col])
        subcategory = _clean(row[sub_col])
        description = _clean(row[desc_col])
        if not kind or not category or not subcategory:
            continue
        entry = {"category": category, "subcategory": subcategory, "description": description}
        key = (kind, subcategory.lower())
        if category not in subcat_to_cat[key]:
            subcat_to_cat[key].append(category)
        if kind == KIND_RISK:
            risks.append(entry)
        elif kind == KIND_MITIGATION:
            mitigations.append(entry)

    strength_df = pd.read_csv(_find("*strength*.csv"))
    s_col, r_col = strength_df.columns[0], strength_df.columns[1]
    strength_rubric = []
    for _, row in strength_df.iterrows():
        raw = _clean(row[s_col])
        if not raw:
            continue
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            continue
        strength_rubric.append({"strength": int(digits[0]), "reason": _clean(row[r_col])})

    assumptions_df = pd.read_csv(_find("*assumptions*.csv"))
    a_col = assumptions_df.columns[0]
    assumptions = [_clean(v) for v in assumptions_df[a_col].tolist() if _clean(v)]
    if assumptions and assumptions[0].lower().startswith("what human coders"):
        assumptions = assumptions[1:]

    risk_categories = sorted({r["category"] for r in risks})
    mitigation_categories = sorted({m["category"] for m in mitigations})
    all_categories = sorted(set(risk_categories) | set(mitigation_categories))
    all_subcategories = sorted({r["subcategory"] for r in risks} | {m["subcategory"] for m in mitigations})

    return {
        "risks": risks,
        "mitigations": mitigations,
        "strength_rubric": strength_rubric,
        "assumptions": assumptions,
        "subcat_to_cat": dict(subcat_to_cat),
        "risk_categories": risk_categories,
        "mitigation_categories": mitigation_categories,
        "all_categories": all_categories,
        "all_subcategories": all_subcategories,
    }


def resolve_category(kind: str, subcategory_raw: str, taxonomy: dict) -> tuple[str | None, str]:
    """Resolve (category, cleaned_subcategory) for a human-CSV row.

    Handles three cases:
    - "Legal; Other" form (Alphabet test CSV) → returns ("Legal", "Other")
    - "Legal: Other" form (multi-doc resolved CSV) → returns ("Legal", "Other")
    - Plain "Privacy & Security" form → looks up in (kind, sub) map.

    Returns (None, cleaned_subcategory) if the subcategory cannot be resolved
    (e.g. ambiguous bare "Other" or unknown subcategory).
    """
    raw = (subcategory_raw or "").strip().rstrip(";").rstrip().strip()
    sep_idx = -1
    for sep in (";", ":"):
        idx = raw.find(sep)
        if idx != -1 and (sep_idx == -1 or idx < sep_idx):
            sep_idx = idx
    if sep_idx != -1:
        head = raw[:sep_idx].strip().rstrip(";").strip()
        tail = raw[sep_idx + 1 :].strip().rstrip(";").strip()
        return head, tail

    candidates = taxonomy["subcat_to_cat"].get((kind, raw.lower()), [])
    if len(candidates) == 1:
        return candidates[0], raw
    return None, raw


if __name__ == "__main__":
    t = load_taxonomy()
    print(f"risks: {len(t['risks'])} entries across {len(t['risk_categories'])} categories")
    print(f"mitigations: {len(t['mitigations'])} entries across {len(t['mitigation_categories'])} categories")
    print(f"strength_rubric: {t['strength_rubric']}")
    print(f"assumptions: {t['assumptions']}")
    print(f"subcat map size: {len(t['subcat_to_cat'])}")
    print()
    # Show keys with multiple candidate categories
    ambiguous = {k: v for k, v in t["subcat_to_cat"].items() if len(v) > 1}
    print(f"ambiguous subcategories (multiple categories): {ambiguous}")
