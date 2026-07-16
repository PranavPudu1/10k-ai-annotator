"""Align AI annotations and human-coded labels to sentence anchors.

Two-coder aware: the human DataFrame is the long-format produced by
`src.multi_human_csv.parse_two_coder_csv` — one row per coder per source
row. Each row becomes a human card with `coder` ("A"|"B") and
`coder_name`. anchor_sources gets richer values to drive UI coloring:
  ai, coder_a, coder_b, coders_both, ai_and_a, ai_and_b, ai_and_both
"""
from __future__ import annotations
import json

import pandas as pd

from .normalize import normalize_text, match_key, clean_subcategory
from .taxonomy import resolve_category


def _build_sentence_lookup(sentences: list[dict]) -> tuple[dict, list[tuple[str, str]]]:
    exact: dict[str, str] = {}
    fuzzy: list[tuple[str, str]] = []
    for s in sentences:
        k = match_key(s["text"])
        if not k:
            continue
        exact.setdefault(k, s["anchor_id"])
        fuzzy.append((k, s["anchor_id"]))
    return exact, fuzzy


def _lookup_anchor(query_text: str, exact: dict, fuzzy: list[tuple[str, str]]) -> str | None:
    key = match_key(query_text)
    if not key:
        return None
    if key in exact:
        return exact[key]
    if len(key) >= 80:
        prefix = key[:80]
        for k, aid in fuzzy:
            if k.startswith(prefix):
                return aid
    if len(key) > 40:
        for k, aid in fuzzy:
            if len(k) <= 40:
                continue
            longer, shorter = (len(k), len(key)) if len(k) > len(key) else (len(key), len(k))
            if longer > 1.5 * shorter:
                continue
            if key in k or k in key:
                return aid
    return None


def _classify_anchor(ai: list[dict], human: list[dict]) -> str:
    has_ai = bool(ai)
    coders = {c.get("coder") for c in human if c.get("coder") in ("A", "B")}
    has_a = "A" in coders
    has_b = "B" in coders
    if has_ai and has_a and has_b:
        return "ai_and_both"
    if has_ai and has_a:
        return "ai_and_a"
    if has_ai and has_b:
        return "ai_and_b"
    if has_ai:
        return "ai"
    if has_a and has_b:
        return "coders_both"
    if has_a:
        return "coder_a"
    if has_b:
        return "coder_b"
    return ""


def align(
    sentences: list[dict],
    ai_annotations: list[dict],
    human_df: pd.DataFrame,
    taxonomy: dict,
) -> dict:
    """Return aligned cards keyed by sentence anchor.

    `human_df` columns (from multi_human_csv): company, year, coder,
    coder_name, sentence, kind, subcategory, strength, ...
    """
    exact, fuzzy = _build_sentence_lookup(sentences)

    cards_by_anchor: dict[str, dict] = {}
    unmatched_ai: list[dict] = []
    unmatched_human: list[dict] = []

    for ann in ai_annotations:
        sentence_text = ann.get("sentence", "")
        anchor = _lookup_anchor(sentence_text, exact, fuzzy)
        card = {
            "side": "ai",
            "kind": ann.get("kind"),
            "category": ann.get("category"),
            "subcategory": ann.get("subcategory"),
            "strength": ann.get("strength"),
            "sentence_excerpt": sentence_text[:140],
        }
        # Preserve per-annotation reasoning (V6 emits it; others don't).
        if ann.get("reasoning"):
            card["reasoning"] = ann["reasoning"]
        if anchor is None:
            unmatched_ai.append(card)
            continue
        cards_by_anchor.setdefault(anchor, {"ai": [], "human": []})["ai"].append(card)

    human_unresolved: list[str] = []
    for _, row in human_df.iterrows():
        sentence_text = row.get("sentence", "")
        if not isinstance(sentence_text, str) or not sentence_text.strip():
            continue
        kind = (row.get("kind") or "").strip()
        if not kind:
            continue
        sub_raw = row.get("subcategory", "") or ""
        category, subcategory = resolve_category(kind, sub_raw, taxonomy)
        if category is None:
            human_unresolved.append(f"{kind} / {sub_raw}")
            category = "(unresolved)"
        strength_raw = row.get("strength")
        strength = None
        if strength_raw is not None and not (isinstance(strength_raw, float) and pd.isna(strength_raw)):
            try:
                strength = int(float(strength_raw))
            except (TypeError, ValueError):
                strength = None

        coder = row.get("coder") or ""
        coder_name = row.get("coder_name") or ""

        anchor = _lookup_anchor(sentence_text, exact, fuzzy)
        card = {
            "side": "human",
            "coder": coder,
            "coder_name": coder_name,
            "kind": kind,
            "category": category,
            "subcategory": clean_subcategory(subcategory),
            "strength": strength,
            "sentence_excerpt": normalize_text(sentence_text)[:140],
        }
        if anchor is None:
            unmatched_human.append(card)
            continue
        cards_by_anchor.setdefault(anchor, {"ai": [], "human": []})["human"].append(card)

    anchor_sources: dict[str, str] = {}
    for anchor, sides in cards_by_anchor.items():
        anchor_sources[anchor] = _classify_anchor(sides["ai"], sides["human"])

    # Count anchors by which coders highlighted them.
    anchors_with_a = sum(
        1 for sides in cards_by_anchor.values()
        if any(c.get("coder") == "A" for c in sides["human"])
    )
    anchors_with_b = sum(
        1 for sides in cards_by_anchor.values()
        if any(c.get("coder") == "B" for c in sides["human"])
    )
    anchors_agreement_AB = sum(
        1 for sides in cards_by_anchor.values()
        if any(c.get("coder") == "A" for c in sides["human"])
        and any(c.get("coder") == "B" for c in sides["human"])
    )

    counts = {
        "ai_total": len(ai_annotations),
        "ai_matched": sum(len(v["ai"]) for v in cards_by_anchor.values()),
        "ai_unmatched": len(unmatched_ai),
        "human_total": int(human_df["sentence"].notna().sum()) if "sentence" in human_df.columns else 0,
        "human_a_total": int((human_df["coder"] == "A").sum()) if "coder" in human_df.columns else 0,
        "human_b_total": int((human_df["coder"] == "B").sum()) if "coder" in human_df.columns else 0,
        "human_matched": sum(len(v["human"]) for v in cards_by_anchor.values()),
        "human_unmatched": len(unmatched_human),
        "anchors_with_ai": sum(1 for s in anchor_sources.values() if s.startswith("ai")),
        "anchors_with_human": sum(
            1 for s in anchor_sources.values()
            if s in ("coder_a", "coder_b", "coders_both", "ai_and_a", "ai_and_b", "ai_and_both")
        ),
        "anchors_with_a": anchors_with_a,
        "anchors_with_b": anchors_with_b,
        "anchors_with_both_coders": anchors_agreement_AB,
        "anchors_with_ai_and_human": sum(
            1 for s in anchor_sources.values()
            if s in ("ai_and_a", "ai_and_b", "ai_and_both")
        ),
        "human_subcategory_unresolved": human_unresolved,
    }
    return {
        "cards_by_anchor": cards_by_anchor,
        "anchor_sources": anchor_sources,
        "unmatched_ai": unmatched_ai,
        "unmatched_human": unmatched_human,
        "counts": counts,
    }


def write_aligned(aligned: dict, aligned_path) -> None:
    aligned_path.parent.mkdir(parents=True, exist_ok=True)
    aligned_path.write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8")
