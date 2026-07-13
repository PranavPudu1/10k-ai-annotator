"""Metric computation for the Evaluation tab.

Pure functions; no Streamlit imports. Operates on the pre-computed
`aligned.json` and `sentences.json` structures.

Multi-coder semantics: human cards now carry a `coder` field ("A"|"B").
`build_sentence_label_frame(..., coder_filter=...)` collapses humans
according to one of four modes:

  - "union" (default): a category counts as human if either coder marked it.
  - "intersection": both coders must mark the same category to count.
  - "coder_a": only Coder A's labels.
  - "coder_b": only Coder B's labels.

Union is the default because it matches the existing single-coder
metric semantics best (any human eye saw this as relevant) and keeps
support high enough to compute meaningful per-category numbers.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    classification_report,
    cohen_kappa_score,
    precision_recall_fscore_support,
)


_KIND_MITIGATION = "Risk Mitigation"
_STRENGTH_LABELS = ["none", "1", "2", "3"]

CODER_FILTERS = ("union", "intersection", "coder_a", "coder_b")


def _max_strength(cards: list[dict]) -> int | None:
    vals = [c.get("strength") for c in cards if isinstance(c.get("strength"), int)]
    return max(vals) if vals else None


def _filter_human_cards(cards: list[dict], coder_filter: str) -> list[dict]:
    """Apply the coder_filter mode to a list of human cards for one anchor.

    For "intersection" we keep only cards whose (kind, category, subcategory)
    appears in BOTH coders' contributions for the anchor. This means a
    category that A tagged with subcategory X and B tagged with subcategory Y
    still counts as agreement at the category level — that decision is taken
    at frame-build time by category-set intersection, which is more useful
    than requiring identical subcategories for inter-coder eval.
    """
    if not cards:
        return []
    if coder_filter == "union":
        return cards
    if coder_filter == "coder_a":
        return [c for c in cards if c.get("coder") == "A"]
    if coder_filter == "coder_b":
        return [c for c in cards if c.get("coder") == "B"]
    if coder_filter == "intersection":
        a_cats = {c.get("category") for c in cards if c.get("coder") == "A"}
        b_cats = {c.get("category") for c in cards if c.get("coder") == "B"}
        agreed = a_cats & b_cats
        return [c for c in cards if c.get("category") in agreed]
    raise ValueError(f"unknown coder_filter: {coder_filter}")


def build_sentence_label_frame(
    aligned: dict,
    sentences: list[dict],
    taxonomy: dict,
    coder_filter: str = "union",
) -> pd.DataFrame:
    """One row per anchor (matched + pseudo-rows for fully-unmatched cards)."""
    sent_by_id = {s["anchor_id"]: s["text"] for s in sentences}
    rows: list[dict[str, Any]] = []

    for anchor_id, sides in aligned.get("cards_by_anchor", {}).items():
        ai_cards = sides.get("ai", []) or []
        human_cards = _filter_human_cards(sides.get("human", []) or [], coder_filter)
        rows.append(
            {
                "anchor_id": anchor_id,
                "sentence_text": sent_by_id.get(anchor_id, ""),
                "ai_categories": {c["category"] for c in ai_cards if c.get("category")},
                "human_categories": {c["category"] for c in human_cards if c.get("category")},
                "ai_kinds": {c["kind"] for c in ai_cards if c.get("kind")},
                "human_kinds": {c["kind"] for c in human_cards if c.get("kind")},
                "ai_strength_max": _max_strength(ai_cards),
                "human_strength_max": _max_strength(human_cards),
                "ai_subcats": {c.get("subcategory") for c in ai_cards if c.get("subcategory")},
                "human_subcats": {c.get("subcategory") for c in human_cards if c.get("subcategory")},
            }
        )

    for idx, card in enumerate(aligned.get("unmatched_ai", []) or []):
        rows.append(
            {
                "anchor_id": f"unmatched_ai_{idx}",
                "sentence_text": card.get("sentence_excerpt", ""),
                "ai_categories": {card["category"]} if card.get("category") else set(),
                "human_categories": set(),
                "ai_kinds": {card["kind"]} if card.get("kind") else set(),
                "human_kinds": set(),
                "ai_strength_max": card["strength"] if isinstance(card.get("strength"), int) else None,
                "human_strength_max": None,
                "ai_subcats": {card["subcategory"]} if card.get("subcategory") else set(),
                "human_subcats": set(),
            }
        )

    for idx, card in enumerate(aligned.get("unmatched_human", []) or []):
        if coder_filter == "coder_a" and card.get("coder") != "A":
            continue
        if coder_filter == "coder_b" and card.get("coder") != "B":
            continue
        # For "intersection" with unmatched human cards we can't verify both
        # coders saw the same sentence, so we skip — they don't count for IAA.
        if coder_filter == "intersection":
            continue
        rows.append(
            {
                "anchor_id": f"unmatched_human_{idx}",
                "sentence_text": card.get("sentence_excerpt", ""),
                "ai_categories": set(),
                "human_categories": {card["category"]} if card.get("category") else set(),
                "ai_kinds": set(),
                "human_kinds": {card["kind"]} if card.get("kind") else set(),
                "ai_strength_max": None,
                "human_strength_max": card["strength"] if isinstance(card.get("strength"), int) else None,
                "ai_subcats": set(),
                "human_subcats": {card["subcategory"]} if card.get("subcategory") else set(),
            }
        )

    return pd.DataFrame(rows)


def build_multilabel_matrices(
    frame: pd.DataFrame, all_categories: list[str]
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    labels = list(all_categories)
    idx = {c: i for i, c in enumerate(labels)}
    n = len(frame)
    y_true = np.zeros((n, len(labels)), dtype=int)
    y_pred = np.zeros((n, len(labels)), dtype=int)
    for row_i, (_, row) in enumerate(frame.iterrows()):
        for c in row["human_categories"]:
            if c in idx:
                y_true[row_i, idx[c]] = 1
        for c in row["ai_categories"]:
            if c in idx:
                y_pred[row_i, idx[c]] = 1
    return y_true, y_pred, labels


def per_category_report(
    y_true: np.ndarray, y_pred: np.ndarray, label_names: list[str]
) -> pd.DataFrame:
    report = classification_report(
        y_true, y_pred, target_names=label_names,
        output_dict=True, zero_division=0,
    )
    rows = []
    for cat in label_names:
        entry = report.get(cat, {})
        rows.append(
            {
                "category": cat,
                "support": int(entry.get("support", 0)),
                "precision": entry.get("precision", 0.0),
                "recall": entry.get("recall", 0.0),
                "f1": entry.get("f1-score", 0.0),
            }
        )
    df = pd.DataFrame(rows).sort_values("support", ascending=False).reset_index(drop=True)
    ai_pred_counts = y_pred.sum(axis=0)
    pred_by_label = dict(zip(label_names, ai_pred_counts))

    def _fmt(row: pd.Series) -> pd.Series:
        out = row.copy()
        if row["support"] == 0:
            out["recall"] = "—"
            out["f1"] = "—"
        if pred_by_label.get(row["category"], 0) == 0:
            out["precision"] = "—"
            out["f1"] = "—"
        for k in ("precision", "recall", "f1"):
            v = out[k]
            if isinstance(v, float):
                out[k] = f"{v:.2f}"
        return out

    return df.apply(_fmt, axis=1)


def aggregate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    out: dict[str, tuple[float, float, float]] = {}
    for avg in ("micro", "macro", "weighted"):
        p, r, f1, _ = precision_recall_fscore_support(
            y_true, y_pred, average=avg, zero_division=0
        )
        out[avg] = (float(p), float(r), float(f1))
    return out


def inter_coder_agreement(
    aligned: dict, taxonomy: dict
) -> dict:
    """Cohen's kappa between Coder A and Coder B over per-(anchor, category) binary labels.

    For each anchor with at least one human card AND at least one of (A, B)
    represented, build a binary indicator per category in the taxonomy:
    1 if that coder tagged that anchor with that category, 0 otherwise.
    Kappa is computed over the flattened (anchor × category) vector.
    """
    categories = list(taxonomy["all_categories"])
    if not categories:
        return {"kappa": None, "n_anchors": 0, "n_pairs": 0, "agreement_anchors": 0}

    a_labels: list[int] = []
    b_labels: list[int] = []
    n_anchors = 0
    agreement_anchors = 0
    cat_idx = {c: i for i, c in enumerate(categories)}

    for anchor_id, sides in aligned.get("cards_by_anchor", {}).items():
        human = sides.get("human", []) or []
        if not human:
            continue
        a_cats = {c.get("category") for c in human if c.get("coder") == "A" and c.get("category")}
        b_cats = {c.get("category") for c in human if c.get("coder") == "B" and c.get("category")}
        if not (a_cats or b_cats):
            continue
        n_anchors += 1
        if a_cats and b_cats and a_cats == b_cats:
            agreement_anchors += 1
        for cat in categories:
            a_labels.append(1 if cat in a_cats else 0)
            b_labels.append(1 if cat in b_cats else 0)

    if not a_labels:
        return {"kappa": None, "n_anchors": 0, "n_pairs": 0, "agreement_anchors": 0}

    kappa = float(cohen_kappa_score(a_labels, b_labels))
    return {
        "kappa": kappa,
        "n_anchors": n_anchors,
        "n_pairs": len(a_labels),
        "agreement_anchors": agreement_anchors,
    }


def strength_confusion(frame: pd.DataFrame) -> tuple[np.ndarray, list[str], str]:
    mit_mask = frame.apply(
        lambda r: (_KIND_MITIGATION in r["ai_kinds"])
        or (_KIND_MITIGATION in r["human_kinds"]),
        axis=1,
    )
    sub = frame[mit_mask] if len(frame) else frame
    mat = np.zeros((4, 4), dtype=int)

    def _bucket(v: object) -> int:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return 0
        return int(v)

    for _, row in sub.iterrows():
        r = _bucket(row["human_strength_max"])
        c = _bucket(row["ai_strength_max"])
        mat[r, c] += 1

    masked = mat.copy()
    np.fill_diagonal(masked, 0)
    if masked.sum() == 0:
        interp = "No off-diagonal disagreement: every mitigation-tagged sentence has matching human and AI strength."
    else:
        r, c = np.unravel_index(masked.argmax(), masked.shape)
        n = int(masked[r, c])
        human_lbl = _STRENGTH_LABELS[r]
        ai_lbl = _STRENGTH_LABELS[c]
        if human_lbl == "none":
            interp = (
                f"Most concerning off-diagonal cell: {n} sentences where the AI "
                f"assigned strength {ai_lbl} but the human did not label the sentence "
                f"as a mitigation at all."
            )
        elif ai_lbl == "none":
            interp = (
                f"Most concerning off-diagonal cell: {n} sentences where the human "
                f"assigned strength {human_lbl} but the AI did not label the sentence "
                f"as a mitigation."
            )
        else:
            interp = (
                f"Most concerning off-diagonal cell: {n} sentences rated strength "
                f"{human_lbl} by humans but strength {ai_lbl} by AI."
            )
    return mat, list(_STRENGTH_LABELS), interp


def category_confusion_matrix(
    frame: pd.DataFrame, all_categories: list[str]
) -> tuple[np.ndarray, list[str]]:
    labels = ["none"] + list(all_categories)
    idx = {label: i for i, label in enumerate(labels)}
    n = len(labels)
    mat = np.zeros((n, n), dtype=int)
    none_i = idx["none"]

    for _, row in frame.iterrows():
        h = row["human_categories"]
        a = row["ai_categories"]
        if not h and not a:
            continue
        if not h:
            for cat in a:
                if cat in idx:
                    mat[none_i, idx[cat]] += 1
        elif not a:
            for cat in h:
                if cat in idx:
                    mat[idx[cat], none_i] += 1
        else:
            for h_cat in h:
                for a_cat in a:
                    if h_cat in idx and a_cat in idx:
                        mat[idx[h_cat], idx[a_cat]] += 1
    return mat, labels


def interpret_category_matrix(mat: np.ndarray, labels: list[str]) -> str:
    none_i = labels.index("none")

    top_row = mat[none_i].copy(); top_row[none_i] = 0
    left_col = mat[:, none_i].copy(); left_col[none_i] = 0

    interior = mat.copy()
    interior[none_i, :] = 0
    interior[:, none_i] = 0
    diag = np.diag(interior).copy()
    off_diag = interior.copy()
    np.fill_diagonal(off_diag, 0)

    parts: list[str] = []
    if top_row.sum() > 0:
        i = int(top_row.argmax())
        parts.append(
            f"**Over-tagging:** AI most often invented a '{labels[i]}' label "
            f"on sentences the human did not tag ({int(top_row[i])} cases)."
        )
    if left_col.sum() > 0:
        i = int(left_col.argmax())
        parts.append(
            f"**Missed:** human most often labeled '{labels[i]}' on sentences "
            f"the AI ignored ({int(left_col[i])} cases)."
        )
    if diag.sum() > 0:
        i = int(diag.argmax())
        parts.append(
            f"**Best agreement:** '{labels[i]}' — {int(diag[i])} sentences "
            f"where both sides picked the same category."
        )
    if off_diag.sum() > 0:
        r, c = np.unravel_index(int(off_diag.argmax()), off_diag.shape)
        parts.append(
            f"**Category confusion:** {int(off_diag[r, c])} sentence(s) the "
            f"human labeled '{labels[r]}' but AI labeled '{labels[c]}'."
        )
    else:
        parts.append(
            "**Category confusion:** none — when both sides tagged a "
            "sentence, they always agreed on the category."
        )
    return " ".join(parts)


def false_positive_category_counts(frame: pd.DataFrame) -> pd.DataFrame:
    counts: dict[str, int] = {}
    for _, row in frame.iterrows():
        if row["human_categories"]:
            continue
        for c in row["ai_categories"]:
            counts[c] = counts.get(c, 0) + 1
    if not counts:
        return pd.DataFrame(columns=["category", "fp_count"])
    return pd.DataFrame(
        sorted(counts.items(), key=lambda kv: kv[1], reverse=True),
        columns=["category", "fp_count"],
    )


def per_sentence_comparison_table(
    frame: pd.DataFrame, all_categories: list[str]
) -> pd.DataFrame:
    def _agreement(ai: set, h: set) -> str:
        if not ai and not h:
            return "none"
        if not h:
            return "ai_only"
        if not ai:
            return "human_only"
        if ai == h:
            return "exact"
        if ai & h:
            return "partial"
        return "disjoint"

    def _join(s: set) -> str:
        return "; ".join(sorted(x for x in s if x))

    out = pd.DataFrame(
        {
            "anchor_id": frame["anchor_id"],
            "sentence": frame["sentence_text"],
            "ai_categories": frame["ai_categories"].map(_join),
            "human_categories": frame["human_categories"].map(_join),
            "ai_subcategories": frame["ai_subcats"].map(_join),
            "human_subcategories": frame["human_subcats"].map(_join),
            "ai_strength": frame["ai_strength_max"],
            "human_strength": frame["human_strength_max"],
            "agreement": [
                _agreement(ai, h)
                for ai, h in zip(frame["ai_categories"], frame["human_categories"])
            ],
        }
    )
    return out
