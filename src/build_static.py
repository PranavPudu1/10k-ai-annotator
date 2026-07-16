"""Render the multi-doc / multi-version reading view to a static `dist/` folder.

Layout:
    dist/index.html                            — top-level directory of docs
    dist/{slug}/index.html                     — per-doc landing (versions list)
    dist/{slug}/{version_id}/index.html        — Document View
    dist/{slug}/{version_id}/annotations.html  — All Annotations
    dist/{slug}/{version_id}/evaluation.html   — Evaluation
    dist/ai_only/...                           — flat AI-only CSVs
    dist/ai_only.zip                           — nested Company/Year.csv zip

Run: `python -m src.build_static`
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px

_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import TEMPLATES_DIR, versioned_paths_for
from src.evaluation import (
    aggregate_metrics,
    build_multilabel_matrices,
    build_sentence_label_frame,
    category_confusion_matrix,
    false_positive_category_counts,
    interpret_category_matrix,
    per_category_report,
    per_sentence_comparison_table,
)
from src.export_ai_only import main as export_ai_only
from src.multi_human_csv import coder_names_for_doc, load_human_for_doc
from src.registry import discover_docs
from src.render_helpers import (
    build_annotations_rows,
    build_cards,
    build_paragraphs,
    legend_for_doc,
)
from src.strategies import STRATEGIES
from src.taxonomy import load_taxonomy

DIST_DIR = _PROJECT_ROOT / "dist"


def _load_version(doc, version_id):
    v = versioned_paths_for(doc.slug, version_id)
    aligned = json.loads(v["aligned_path"].read_text(encoding="utf-8"))
    meta = json.loads(v["meta_path"].read_text(encoding="utf-8")) if v["meta_path"].exists() else {}
    return aligned, meta


def _build_one_version(env, taxonomy, doc, version_id, shared) -> dict:
    """Render the 3 pages for one (doc, version)."""
    aligned, meta = _load_version(doc, version_id)
    out_dir = DIST_DIR / doc.slug / version_id
    out_dir.mkdir(parents=True, exist_ok=True)

    counts = dict(aligned["counts"])
    paragraphs = build_paragraphs(shared["text"], shared["sentences"], aligned["anchor_sources"])
    ai_cards = build_cards(aligned["cards_by_anchor"], shared["sentences"], "ai")
    human_cards = build_cards(aligned["cards_by_anchor"], shared["sentences"], "human")
    rows = build_annotations_rows(aligned, shared["sentences"])

    strategy = STRATEGIES.get(version_id)
    version_name = strategy.label() if strategy else version_id
    page_title = f"{doc.company_display} {doc.year} 10-K · {version_name}"
    legend_html = legend_for_doc(shared["coder_names"].get("A", ""), shared["coder_names"].get("B", ""))

    common_render_args = {
        "page_title": page_title,
        "legend_html": legend_html,
        "version_id": version_id,
        "version_name": version_name,
        "version_description": meta.get("description", strategy.description if strategy else ""),
        "doc_landing_href": "../index.html",
        "coder_a_name": shared["coder_names"].get("A", ""),
        "coder_b_name": shared["coder_names"].get("B", ""),
    }

    doc_html = env.get_template("static_document.html.j2").render(
        active_tab="document",
        paragraphs=paragraphs,
        ai_cards=ai_cards,
        human_cards=human_cards,
        unmatched_ai=aligned["unmatched_ai"],
        unmatched_human=aligned["unmatched_human"],
        counts=counts,
        **common_render_args,
    )
    (out_dir / "index.html").write_text(doc_html, encoding="utf-8")

    pd.DataFrame(rows).to_csv(out_dir / "all_annotations.csv", index=False)

    ann_html = env.get_template("static_annotations.html.j2").render(
        active_tab="annotations",
        rows=rows,
        counts=counts,
        **common_render_args,
    )
    (out_dir / "annotations.html").write_text(ann_html, encoding="utf-8")

    eval_html = _build_evaluation_page(
        env, taxonomy, aligned, shared["sentences"], counts, out_dir, common_render_args,
    )
    (out_dir / "evaluation.html").write_text(eval_html, encoding="utf-8")

    missed_html = _build_missed_page(doc, version_id, aligned, shared["sentences"], common_render_args)
    (out_dir / "missed.html").write_text(missed_html, encoding="utf-8")

    return {
        "version_id": version_id,
        "version_name": version_name,
        "ai_total": counts.get("ai_total", 0),
        "anchors_with_ai": counts.get("anchors_with_ai", 0),
        "anchors_with_ai_and_human": counts.get("anchors_with_ai_and_human", 0),
    }


def _missed_diagnoses(doc, version_id: str, missed_anchor_ids: list[str], aligned: dict, sentences: list[dict]) -> dict[str, str]:
    """Per-anchor diagnosis of WHY each missed anchor wasn't caught.

    For sequential workflows (V3 sequential_batched, V5 sequential_passage_aware),
    inspect the cached per-phase responses to trace where each anchor was lost
    (passage / candidate / filter / kind / category). For single-call workflows
    (V0 baseline, V1, V2, V4, V4.1), the diagnosis is just "AI didn't tag this
    sentence" — there are no phase boundaries to trace.
    """
    diagnoses: dict[str, str] = {}
    anchor_order = {s["anchor_id"]: i for i, s in enumerate(sentences)}
    paths = versioned_paths_for(doc.slug, version_id)
    cache_path = paths["llm_raw_path"]
    if not cache_path.exists():
        return {aid: "AI did not tag this sentence (no per-phase trace available)." for aid in missed_anchor_ids}

    try:
        cache_list = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {aid: "AI did not tag this sentence (cache unreadable)." for aid in missed_anchor_ids}

    # Single-call strategies have a {"choices": [...]} cache, not a list of phases.
    if not isinstance(cache_list, list):
        return {aid: "This strategy doesn't have per-phase tracing — the AI simply didn't include this sentence in its annotations output." for aid in missed_anchor_ids}

    # V1/V2 use {"chunk_id": ..., "raw_response": ...} entries — no "phase" key.
    # V3/V5 use {"phase": ..., "raw_response": ...}. Only the latter has per-phase tracing.
    by_phase = {
        entry["phase"]: entry["raw_response"]
        for entry in cache_list
        if isinstance(entry, dict) and "phase" in entry
    }

    def _content(phase_id):
        raw = by_phase.get(phase_id)
        if not raw:
            return None
        try:
            return json.loads(raw["choices"][0]["message"]["content"])
        except (KeyError, json.JSONDecodeError):
            return None

    # V5 phase IDs: p1_passages, p2_outside_mentions, p3_context_filter, p4_kind, p5a_risk_cats, p5b_mit_cats, p6_strength
    # V3 phase IDs: p1_candidates, p2_kind, p3a_risk_cats, p3b_mit_cats, p4_strength
    if "p1_passages" in by_phase:
        # V5 trace
        p1 = _content("p1_passages") or {"passages": []}
        p2 = _content("p2_outside_mentions") or {"verdicts": []}
        p3 = _content("p3_context_filter") or {"verdicts": []}
        p4 = _content("p4_kind") or {"verdicts": []}
        p5a = _content("p5a_risk_cats") or {"verdicts": []}
        p5b = _content("p5b_mit_cats") or {"verdicts": []}

        passages = []
        for p in p1.get("passages", []):
            if p.get("start_anchor") in anchor_order and p.get("end_anchor") in anchor_order:
                lo, hi = anchor_order[p["start_anchor"]], anchor_order[p["end_anchor"]]
                if hi < lo:
                    lo, hi = hi, lo
                passages.append((lo, hi, p.get("topic_summary", "")))
        def _in_passage(aid):
            if aid not in anchor_order:
                return None
            i = anchor_order[aid]
            for lo, hi, summary in passages:
                if lo <= i <= hi:
                    return summary
            return None

        p2_mentions = {v.get("anchor_id") for v in p2.get("verdicts", [])}
        p3_verdicts = {v.get("anchor_id"): v for v in p3.get("verdicts", [])}
        p4_verdicts = {v.get("anchor_id"): v.get("kind") for v in p4.get("verdicts", [])}
        p5a_kept = {v.get("anchor_id") for v in p5a.get("verdicts", [])}
        p5b_kept = {v.get("anchor_id") for v in p5b.get("verdicts", [])}

        for aid in missed_anchor_ids:
            passage_summary = _in_passage(aid)
            in_p2 = aid in p2_mentions
            p3v = p3_verdicts.get(aid)
            p4v = p4_verdicts.get(aid)
            in_p5a = aid in p5a_kept
            in_p5b = aid in p5b_kept
            if not passage_summary and not in_p2:
                diagnoses[aid] = "P1+P2: Not surfaced as a candidate — the sentence was not inside any AI-topic passage Phase 1 identified, and Phase 2 didn't flag it as a direct AI mention."
            elif p3v is None:
                diagnoses[aid] = "Pre-P3: Candidate was in the set but Phase 3 didn't issue a verdict on it."
            elif not p3v.get("keep"):
                reason = (p3v.get("reason") or "").strip()
                diagnoses[aid] = f"P3 (context filter): DROPPED — reason given: \"{reason}\""
            elif p4v is None:
                diagnoses[aid] = "Pre-P4: Phase 3 kept it but Phase 4 didn't issue a kind verdict."
            elif p4v not in ("Risk", "Risk Mitigation"):
                diagnoses[aid] = f"P4 (kind decision): kind set to null — Phase 4 decided it wasn't a Risk or Mitigation."
            elif not in_p5a and not in_p5b:
                diagnoses[aid] = "P5 (category assignment): Made it through filtering but Phase 5 didn't return a (category, subcategory) tuple."
            else:
                diagnoses[aid] = "Tagged by AI but at a different (kind, category, subcategory) than the human — see Document View for the actual AI tags."
    elif "p1_candidates" in by_phase:
        # V3 trace
        p1 = _content("p1_candidates") or {"verdicts": []}
        p2 = _content("p2_kind") or {"verdicts": []}
        p3a = _content("p3a_risk_cats") or {"verdicts": []}
        p3b = _content("p3b_mit_cats") or {"verdicts": []}
        p1_set = {v.get("anchor_id") for v in p1.get("verdicts", [])}
        p2_kept = {v.get("anchor_id"): v.get("kind") for v in p2.get("verdicts", [])}
        p3_kept = {v.get("anchor_id") for v in p3a.get("verdicts", [])} | {v.get("anchor_id") for v in p3b.get("verdicts", [])}
        for aid in missed_anchor_ids:
            if aid not in p1_set:
                diagnoses[aid] = "P1 (candidates): The candidate-identification pass didn't list this sentence as AI-related."
            elif aid not in p2_kept or p2_kept[aid] not in ("Risk", "Risk Mitigation"):
                kind = p2_kept.get(aid)
                diagnoses[aid] = f"P2 (kind decision): Filtered as null/non-RAI (returned kind={kind!r})."
            elif aid not in p3_kept:
                diagnoses[aid] = "P3 (category assignment): No category was returned for this sentence."
            else:
                diagnoses[aid] = "Tagged by AI but at a different (kind, category, subcategory) than the human."
    else:
        for aid in missed_anchor_ids:
            diagnoses[aid] = "This strategy doesn't have per-phase tracing — the AI simply didn't include this sentence in its annotations output."
    return diagnoses


def _build_missed_page(doc, version_id: str, aligned: dict, sentences: list[dict], common_render_args: dict) -> str:
    """Per-version diagnostic page: missed human anchors + per-anchor diagnosis."""
    sent_by_id = {s["anchor_id"]: s["text"] for s in sentences}
    cards = aligned.get("cards_by_anchor", {})

    missed: list[dict] = []  # {anchor_id, sentence, human_tags, diagnosis}
    for anchor_id, sides in cards.items():
        human_cards = sides.get("human", []) or []
        ai_cards = sides.get("ai", []) or []
        if human_cards and not ai_cards:
            missed.append({
                "anchor_id": anchor_id,
                "sentence": sent_by_id.get(anchor_id, ""),
                "human_tags": [(c.get("kind"), c.get("category"), c.get("subcategory")) for c in human_cards],
            })

    diagnoses = _missed_diagnoses(doc, version_id, [m["anchor_id"] for m in missed], aligned, sentences)
    for m in missed:
        m["diagnosis"] = diagnoses.get(m["anchor_id"], "(no diagnosis)")

    unmatched_human = aligned.get("unmatched_human", []) or []

    # Aggregate by where it was lost for the headline summary
    from collections import Counter
    bucket_counts = Counter()
    for m in missed:
        bucket = m["diagnosis"].split(":", 1)[0]
        bucket_counts[bucket] += 1
    bucket_counts["Unmatched human (extraction-side, can't be caught)"] = len(unmatched_human)

    counts = aligned.get("counts", {})
    summary_box = f"""
<div class="metric-row">
  <div class="metric-card"><div class="label">Human anchors total</div>
    <div class="value">{counts.get('anchors_with_human', 0) + len(unmatched_human)}</div>
    <div class="sub">{counts.get('anchors_with_human', 0)} matched + {len(unmatched_human)} unmatched</div></div>
  <div class="metric-card"><div class="label">Caught by AI</div>
    <div class="value">{counts.get('anchors_with_ai_and_human', 0)}</div></div>
  <div class="metric-card"><div class="label">Missed by AI</div>
    <div class="value">{len(missed) + len(unmatched_human)}</div></div>
</div>
"""

    bucket_rows = "".join(
        f"<tr><td class='num'>{n}</td><td>{bucket}</td></tr>"
        for bucket, n in bucket_counts.most_common()
    )

    # For V3/V5, extract the AI's reasoning text separately so we can render it
    # as CoT (highlighted, italicized) — this is the "thinking trace" the notes
    # doc asked for. V3 phase names: p1_candidates, p2_kind, p3a/b, p4_strength.
    # V5 phase names: p1_passages, p2_outside_mentions, p3_context_filter, ...
    # We look for `reason` fields on P3 verdicts specifically.
    ai_reasoning: dict[str, str] = {}
    v_paths = versioned_paths_for(doc.slug, version_id)
    if v_paths["llm_raw_path"].exists():
        try:
            cache_list = json.loads(v_paths["llm_raw_path"].read_text(encoding="utf-8"))
            if isinstance(cache_list, list):
                by_phase = {
                    e["phase"]: e["raw_response"] for e in cache_list
                    if isinstance(e, dict) and "phase" in e
                }
                p3_raw = by_phase.get("p3_context_filter")
                if p3_raw:
                    try:
                        p3_parsed = json.loads(p3_raw["choices"][0]["message"]["content"])
                        for v in p3_parsed.get("verdicts", []):
                            aid = v.get("anchor_id")
                            reason = (v.get("reason") or "").strip()
                            if aid and reason:
                                ai_reasoning[aid] = reason
                    except (KeyError, json.JSONDecodeError):
                        pass
        except (json.JSONDecodeError, OSError):
            pass

    missed_rows = ""
    for m in missed:
        tag_lines = "<br>".join(
            f"<span class='tag-line'>{k} / {c} / {s}</span>"
            for k, c, s in m["human_tags"]
        )
        # If we have an explicit AI reasoning trace from V5's Phase 3, show it as
        # a highlighted CoT block below the diagnosis line.
        cot_block = ""
        reason = ai_reasoning.get(m["anchor_id"])
        if reason:
            cot_block = f'<div class="ai-cot"><span class="ai-cot-label">AI reasoning (V5 Phase 3):</span> <em>{reason.replace("<", "&lt;")}</em></div>'
        missed_rows += f"""
<tr>
  <td class="anchor-cell">{m['anchor_id']}</td>
  <td class="sentence-cell">{m['sentence'][:600].replace('<', '&lt;')}</td>
  <td class="tag-cell">{tag_lines}</td>
  <td class="reason-cell">{m['diagnosis'].replace('<', '&lt;')}{cot_block}</td>
</tr>
"""

    if unmatched_human:
        for c in unmatched_human:
            kind = c.get("kind", "")
            cat = c.get("category", "")
            sub = c.get("subcategory", "")
            sent = (c.get("sentence_excerpt") or "").replace("<", "&lt;")
            missed_rows += f"""
<tr>
  <td class="anchor-cell">(unmatched)</td>
  <td class="sentence-cell">{sent}</td>
  <td class="tag-cell"><span class='tag-line'>{kind} / {cat} / {sub}</span></td>
  <td class="reason-cell">Unmatched human (extraction-side): the human-annotated sentence text didn't align to any sentence in our extracted doc. Cannot be caught by any AI version.</td>
</tr>
"""

    body = f"""
<style>
  .missed-content {{ padding: 20px 24px 80px; max-width: 1300px; margin: 0 auto; }}
  .missed-content h2 {{ font-size: 20px; font-weight: 600; margin: 28px 0 10px; color: #1c1917; }}
  .missed-content p {{ font-size: 14px; line-height: 1.55; color: #292524; margin: 8px 0; }}
  .metric-row {{ display: flex; gap: 16px; margin: 12px 0 8px; flex-wrap: wrap; }}
  .metric-card {{ background: white; border: 1px solid #e7e5e4; border-radius: 8px;
    padding: 14px 18px; flex: 1 1 200px; min-width: 180px; }}
  .metric-card .label {{ font-size: 12px; color: #57534e; }}
  .metric-card .value {{ font-size: 28px; font-weight: 600; color: #1c1917; margin-top: 4px; }}
  .metric-card .sub {{ font-size: 12px; color: #78716c; margin-top: 2px; }}
  table.bucket, table.missed-table {{
    width: 100%; border-collapse: collapse; margin: 8px 0 16px;
    font-size: 13px; background: white; border: 1px solid #e7e5e4; border-radius: 6px;
  }}
  table.bucket th, table.bucket td, table.missed-table th, table.missed-table td {{
    padding: 8px 12px; text-align: left; border-bottom: 1px solid #f5f5f4; vertical-align: top;
  }}
  table.bucket th, table.missed-table th {{ background: #f5f5f4; font-weight: 600; color: #44403c; }}
  table.bucket td.num, table.missed-table td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .anchor-cell {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; color: #44403c; white-space: nowrap; width: 80px; }}
  .sentence-cell {{ color: #1c1917; max-width: 380px; }}
  .tag-cell {{ color: #44403c; font-size: 12px; max-width: 260px; }}
  .tag-line {{ display: block; padding: 2px 6px; background: rgba(234, 88, 12, 0.08);
    border-left: 2px solid #ea580c; margin: 2px 0; border-radius: 2px; }}
  .reason-cell {{ color: #1c1917; font-size: 13px; max-width: 380px; }}
  .ai-cot {{ margin-top: 8px; padding: 8px 10px; background: rgba(37, 99, 235, 0.06);
    border-left: 3px solid #2563eb; border-radius: 3px; font-size: 12px; color: #1e40af; }}
  .ai-cot-label {{ font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;
    font-size: 10px; color: #1e40af; display: block; margin-bottom: 3px; }}
</style>
<main class="missed-content">
  <h2>What this page shows</h2>
  <p>
    Every human-tagged sentence in this 10-K that this AI version <strong>did not catch</strong>.
    Each row shows the sentence, the (kind / category / subcategory) the human applied,
    and a diagnosis of where the AI lost this anchor.
    For sequential strategies (V3, V5), the diagnosis traces the candidate through each phase.
    For single-call strategies (V0, V1, V2, V4, V4.1), the AI simply didn't include the sentence
    in its output.
  </p>
  <p style="background: rgba(37, 99, 235, 0.06); border-left: 3px solid #2563eb; padding: 8px 10px; border-radius: 3px;">
    <strong>Chain-of-thought trace:</strong> V5 (passage-aware sequential) renders the model's
    verbatim <em>reasoning</em> from its Phase 3 (context filter) decision, highlighted in blue below each
    diagnosis. V6 (XML CoT) emits per-annotation reasoning too — that appears on the tags V6 <em>did</em>
    emit (see aligned.json), not on missed ones, since V6 is a single-call strategy with no candidate-filtering step.
  </p>

  <h2>Headline counts</h2>
  {summary_box}

  <h2>Where the AI lost the missed anchors</h2>
  <table class="bucket">
    <thead><tr><th class="num">Count</th><th>Where it was lost</th></tr></thead>
    <tbody>{bucket_rows}</tbody>
  </table>

  <h2>Per-anchor detail</h2>
  <table class="missed-table">
    <thead><tr>
      <th>Anchor</th><th>Sentence (first 600 chars)</th>
      <th>Human-applied tag(s)</th><th>Why this version missed it</th>
    </tr></thead>
    <tbody>{missed_rows}</tbody>
  </table>
</main>
"""

    return _PAGE_SHELL.format(
        page_title=common_render_args["page_title"],
        legend_html=common_render_args["legend_html"],
        version_id=common_render_args["version_id"],
        version_description=common_render_args["version_description"],
        doc_landing_href=common_render_args.get("doc_landing_href", "../index.html"),
        body=body,
    )


_PAGE_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title} · Missed Human Tags</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  :root {{ --text-color: #1c1917; }}
  html, body {{ background: #fafaf9; color: #1c1917; }}
  body {{ font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; margin: 0; }}
  .app-header {{ padding: 16px 24px 12px; background: white; border-bottom: 1px solid #e7e5e4; }}
  .app-header h1 {{ font-size: 18px; font-weight: 600; margin: 0; color: #1c1917; }}
  .app-header .nav-back {{ display: inline-block; margin-top: 4px; font-size: 12px; color: #57534e; }}
  .app-header .nav-back a {{ color: #57534e; text-decoration: none; }}
  .app-header .nav-back a:hover {{ color: #1c1917; text-decoration: underline; }}
  details.legend-expander {{ background: white; border: 1px solid #e7e5e4; border-radius: 6px;
    margin: 16px 24px 0; }}
  details.legend-expander > summary {{ cursor: pointer; padding: 10px 14px; font-weight: 600;
    font-size: 14px; color: #1c1917; list-style: none; }}
  details.legend-expander > summary::-webkit-details-marker {{ display: none; }}
  details.legend-expander > .legend-body {{ padding: 0 14px 12px; }}
  .tabs {{ margin: 16px 24px 0; border-bottom: 1px solid #e7e5e4; display: flex; gap: 4px; }}
  .tabs a {{ padding: 8px 16px; font-size: 14px; color: #57534e; text-decoration: none;
    border-bottom: 2px solid transparent; margin-bottom: -1px; }}
  .tabs a:hover {{ color: #1c1917; }}
  .tabs a.active {{ color: #1c1917; font-weight: 600; border-bottom-color: #1c1917; }}
</style>
</head>
<body>
<header class="app-header">
  <h1>{page_title}</h1>
  <p class="nav-back">
    <a href="{doc_landing_href}">&larr; Versions for this doc</a>
    &middot;
    <a href="../../index.html">All documents</a>
  </p>
</header>
<details class="legend-expander">
  <summary>About this version &mdash; {version_id}</summary>
  <div class="legend-body">
    <p style="font-size: 13px; color: #292524; line-height: 1.55;">{version_description}</p>
  </div>
</details>
<nav class="tabs">
  <a href="index.html">Document View</a>
  <a href="annotations.html">All Annotations</a>
  <a href="evaluation.html">Evaluation</a>
  <a href="missed.html" class="active">Missed Human Tags</a>
</nav>
{body}
</body>
</html>
"""


def _build_evaluation_page(env, taxonomy, aligned, sentences, counts, out_dir, common_render_args) -> str:
    frame = build_sentence_label_frame(aligned, sentences, taxonomy, coder_filter="union")
    all_categories = taxonomy["all_categories"]
    y_true, y_pred, label_names = build_multilabel_matrices(frame, all_categories)

    cat_df = per_category_report(y_true, y_pred, label_names)
    per_category_rows = cat_df.to_dict(orient="records")
    agg = aggregate_metrics(y_true, y_pred)

    cmat, clabels = category_confusion_matrix(frame, all_categories)
    fig_conf = px.imshow(
        cmat, x=clabels, y=clabels, text_auto=True,
        labels={"x": "AI said", "y": "Human said", "color": "sentences"},
        color_continuous_scale="Blues", aspect="auto",
    )
    fig_conf.update_xaxes(side="top", tickangle=-40)
    fig_conf.update_layout(height=620, margin=dict(l=160, t=160, r=20, b=20))
    confusion_fig_html = fig_conf.to_html(full_html=False, include_plotlyjs=False, div_id="confusion-matrix")
    confusion_interpretation = interpret_category_matrix(cmat, clabels)

    fp_df = false_positive_category_counts(frame)
    if fp_df.empty:
        fp_fig_html = "<p class='muted'>No AI-only sentences — nothing to plot.</p>"
    else:
        fig_fp = px.bar(
            fp_df, x="fp_count", y="category", orientation="h",
            color="fp_count", color_continuous_scale="Reds",
            labels={"fp_count": "sentences AI tagged but human did not", "category": ""},
        )
        fig_fp.update_layout(
            yaxis={"categoryorder": "total ascending"},
            showlegend=False, coloraxis_showscale=False,
            height=400, margin=dict(l=240, t=20, r=20, b=40),
        )
        fp_fig_html = fig_fp.to_html(full_html=False, include_plotlyjs=False, div_id="fp-bar-chart")

    mit_mask = frame.apply(
        lambda r: ("Risk Mitigation" in r["ai_kinds"])
        or ("Risk Mitigation" in r["human_kinds"]),
        axis=1,
    )
    mit = frame[mit_mask] if len(frame) else frame
    h_levels = sorted({int(v) for v in mit["human_strength_max"] if pd.notna(v)}) if len(mit) else []
    a_levels = sorted({int(v) for v in mit["ai_strength_max"] if pd.notna(v)}) if len(mit) else []

    export_df = per_sentence_comparison_table(frame, all_categories)
    export_df.to_csv(out_dir / "evaluation_per_sentence.csv", index=False)

    return env.get_template("static_evaluation.html.j2").render(
        active_tab="evaluation",
        counts=counts,
        per_category_rows=per_category_rows,
        aggregate=agg,
        confusion_fig_html=confusion_fig_html,
        confusion_interpretation=confusion_interpretation,
        fp_fig_html=fp_fig_html,
        human_strength_levels=h_levels or "∅",
        ai_strength_levels=a_levels or "∅",
        **common_render_args,
    )


def _build_doc_landing(doc, summaries: list[dict]) -> None:
    """Per-doc page listing versions with links."""
    out_dir = DIST_DIR / doc.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_html = []
    for s in summaries:
        rows_html.append(
            f'<tr class="border-t">'
            f'<td class="p-2"><a class="text-blue-700 hover:underline" href="{s["version_id"]}/index.html">{s["version_name"]}</a><div class="text-xs text-stone-500">{s["version_id"]}</div></td>'
            f'<td class="p-2 text-right">{s["ai_total"]}</td>'
            f'<td class="p-2 text-right">{s["anchors_with_ai"]}</td>'
            f'<td class="p-2 text-right">{s["anchors_with_ai_and_human"]}</td>'
            f'</tr>'
        )
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{doc.company_display} {doc.year} — versions</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-stone-50 text-stone-900 font-sans">
<header class="px-6 py-5 border-b bg-white">
  <h1 class="text-xl font-semibold">{doc.company_display} {doc.year} 10-K</h1>
  <p class="text-sm mt-1"><a class="text-blue-700 hover:underline" href="../index.html">&larr; All documents</a></p>
</header>
<main class="max-w-3xl mx-auto p-6">
<p class="text-sm text-stone-600 mb-2">{len(summaries)} AI methodology version(s) available. Pick one to view annotations.</p>
<table class="w-full bg-white border rounded text-sm">
  <thead class="bg-stone-100 text-stone-700">
    <tr><th class="text-left p-2">Version</th><th class="text-right p-2">AI tags</th>
    <th class="text-right p-2">Anchors w/ AI</th><th class="text-right p-2">AI + Human</th></tr>
  </thead>
  <tbody>{''.join(rows_html)}</tbody>
</table>
</main></body></html>"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def _write_top_index(per_doc_summaries: list[dict], all_docs: list) -> None:
    """Top-level index listing every doc with its built versions."""
    built_slugs = {d["slug"] for d in per_doc_summaries}
    rows = []
    for d in all_docs:
        if d.slug in built_slugs:
            s = next(x for x in per_doc_summaries if x["slug"] == d.slug)
            version_str = ", ".join(s["versions"])
            link = f'<a class="text-blue-700 hover:underline" href="{d.slug}/index.html">{d.company_display} {d.year}</a>'
            rows.append({
                "title_cell": link, "status": f"{len(s['versions'])} version(s): {version_str}",
                "ai_total": s["ai_total_first"],
                "human_a_total": s["human_a_total"], "human_b_total": s["human_b_total"],
            })
        else:
            rows.append({
                "title_cell": f"{d.company_display} {d.year}",
                "status": "HTML only" if d.has_html else "no HTML",
                "ai_total": 0, "human_a_total": 0, "human_b_total": 0,
            })

    rows_html = []
    for r in rows:
        rows_html.append(
            f'<tr class="border-t"><td class="p-2">{r["title_cell"]}</td>'
            f'<td class="p-2 text-stone-600">{r["status"]}</td>'
            f'<td class="p-2 text-right">{r["ai_total"]}</td>'
            f'<td class="p-2 text-right">{r["human_a_total"]}</td>'
            f'<td class="p-2 text-right">{r["human_b_total"]}</td></tr>'
        )

    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>RAI 10-K Annotations — Directory</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-stone-50 text-stone-900 font-sans">
<header class="px-6 py-5 border-b bg-white">
  <h1 class="text-xl font-semibold">RAI 10-K Annotations</h1>
  <p class="text-sm text-stone-600 mt-1">{len(per_doc_summaries)} of {len(all_docs)} docs have at least one AI version built.</p>
  <p class="text-sm mt-2">
    <a class="text-blue-700 hover:underline" href="ai_only.zip">Download AI-only annotations (zip, Company/Year.csv)</a>
    &middot;
    <a class="text-blue-700 hover:underline" href="ai_only/all_ai_only.csv">flat combined CSV</a>
  </p>
</header>
<main class="max-w-4xl mx-auto p-6">
<table class="w-full bg-white border rounded text-sm">
  <thead class="bg-stone-100 text-stone-700">
    <tr><th class="text-left p-2">Document</th><th class="text-left p-2">Versions</th>
    <th class="text-right p-2">AI tags</th><th class="text-right p-2">Coder A</th>
    <th class="text-right p-2">Coder B</th></tr>
  </thead>
  <tbody>{''.join(rows_html)}</tbody>
</table>
</main></body></html>"""
    (DIST_DIR / "index.html").write_text(html, encoding="utf-8")


def _human_totals(slug: str) -> tuple[int, int]:
    """Look up Coder A / Coder B totals from any built version's aligned.json."""
    docs = discover_docs()
    doc = next((d for d in docs if d.slug == slug), None)
    if not doc or not doc.versions:
        return 0, 0
    aligned = json.loads(versioned_paths_for(slug, doc.versions[0])["aligned_path"].read_text(encoding="utf-8"))
    c = aligned.get("counts", {})
    return c.get("human_a_total", 0), c.get("human_b_total", 0)


def main() -> None:
    all_docs = discover_docs()
    if not all_docs:
        sys.exit("No docs in registry — check data/10ks/.")
    runnable = [d for d in all_docs if d.has_ai]
    if not runnable:
        sys.exit("No docs have any built AI version. Run `python -m src.pipeline --all --version baseline` first.")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    taxonomy = load_taxonomy()

    per_doc_summaries: list[dict] = []
    for doc in runnable:
        print(f"building {doc.slug} ({len(doc.versions)} version(s))...")
        text = doc.paths["txt_path"].read_text(encoding="utf-8")
        sentences = json.loads(doc.paths["sentences_path"].read_text(encoding="utf-8"))
        human_df = load_human_for_doc(doc.slug)
        coder_names = coder_names_for_doc(human_df)
        shared = {"text": text, "sentences": sentences, "coder_names": coder_names}

        version_summaries = []
        for version_id in doc.versions:
            version_summaries.append(_build_one_version(env, taxonomy, doc, version_id, shared))
        _build_doc_landing(doc, version_summaries)

        a_total, b_total = _human_totals(doc.slug)
        per_doc_summaries.append({
            "slug": doc.slug,
            "versions": [v["version_id"] for v in version_summaries],
            "ai_total_first": version_summaries[0]["ai_total"],
            "human_a_total": a_total,
            "human_b_total": b_total,
        })

    _write_top_index(per_doc_summaries, all_docs)
    print(f"\nWrote {len(per_doc_summaries)} docs to {DIST_DIR}")
    print(f"  index: {DIST_DIR / 'index.html'}")

    print("\nWriting AI-only CSVs (baseline by default; see --version flag in export_ai_only)...")
    export_ai_only(out_dir=DIST_DIR / "ai_only")


if __name__ == "__main__":
    main()
