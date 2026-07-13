"""Text normalization for sentence matching, and annotation validation."""
from __future__ import annotations
import re

_AI_TERM_RE = re.compile(r"\s*AI_TERM\s*[×x*]\s*", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
# Whitespace immediately preceding punctuation is residue from stripping
# AI_TERM× tokens out of constructs like "AI;" or "AI-related" (the human CSV
# stores these as "AI_TERM× ;" / "AI_TERM× -related"). The PDF reads them
# without the gap, so we close it before matching.
_PRE_PUNCT_RE = re.compile(r"\s+([;\-.,:])")
_QUOTE_TR = str.maketrans({
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    " ": " ",
})


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = s.translate(_QUOTE_TR)
    s = _AI_TERM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    s = _PRE_PUNCT_RE.sub(r"\1", s)
    return s


def match_key(s: str) -> str:
    return normalize_text(s).lower()


def clean_subcategory(s: str) -> str:
    if not s:
        return ""
    return s.strip().rstrip(";").rstrip().strip()


def dedupe_annotations(items: list[dict]) -> list[dict]:
    """Drop duplicate annotations across overlapping chunks.

    Key = (normalized sentence text, kind, category, subcategory, strength).
    Keeps the first occurrence in `items` order.
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for it in items:
        key = (
            match_key(it.get("sentence", "")),
            it.get("kind"),
            it.get("category"),
            it.get("subcategory"),
            it.get("strength"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def validate_annotations(items: list[dict], taxonomy: dict) -> tuple[list[dict], dict]:
    """Drop malformed entries (e.g. mitigation with null strength).
    Return (valid_items, counts_dict).
    """
    valid: list[dict] = []
    counts = {
        "total": len(items),
        "kept": 0,
        "dropped_bad_kind": 0,
        "dropped_bad_strength": 0,
        "dropped_unknown_category": 0,
        "dropped_unknown_subcategory": 0,
    }
    risk_cats = set(taxonomy["risk_categories"])
    mit_cats = set(taxonomy["mitigation_categories"])
    all_subs = set(taxonomy["all_subcategories"])

    for it in items:
        kind = it.get("kind")
        cat = it.get("category")
        sub = it.get("subcategory")
        strength = it.get("strength")

        if kind not in ("Risk", "Risk Mitigation"):
            counts["dropped_bad_kind"] += 1
            continue
        if kind == "Risk Mitigation":
            if not isinstance(strength, int) or strength not in (1, 2, 3):
                counts["dropped_bad_strength"] += 1
                continue
            if cat not in mit_cats:
                counts["dropped_unknown_category"] += 1
                continue
        else:  # Risk
            if strength is not None:
                it = {**it, "strength": None}
            if cat not in risk_cats:
                counts["dropped_unknown_category"] += 1
                continue
        if sub not in all_subs:
            counts["dropped_unknown_subcategory"] += 1
            continue
        valid.append(it)

    counts["kept"] = len(valid)
    return valid, counts
