"""Streamlit reading view. Reads pre-computed pipeline outputs.

Sidebar dropdown picks a (Company, Year) doc. Per-doc preflight surfaces
missing HTML / missing aligned.json in plain language and skips
gracefully. Two-coder rendering with per-coder colors.

Run with: `streamlit run src/app.py` from the project root.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# Streamlit runs this as a top-level script (not as part of the `src` package),
# so relative imports won't resolve. Add the project root to sys.path and
# import absolutely.
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.config import TEMPLATES_DIR, versioned_paths_for
from src.evaluation import (
    CODER_FILTERS,
    aggregate_metrics,
    build_multilabel_matrices,
    build_sentence_label_frame,
    category_confusion_matrix,
    false_positive_category_counts,
    inter_coder_agreement,
    interpret_category_matrix,
    per_category_report,
    per_sentence_comparison_table,
)
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

st.set_page_config(layout="wide", page_title="RAI 10-K Annotation Prototype")


EVAL_INTRO_MD = """
We had **humans** and an **AI** label sentences in this 10-K against
the **same predefined taxonomy** of 11 risk and mitigation categories. Both sides
picked from the same menu — neither invented categories on the fly. This tab
quantifies how close the two label sets are.

A quick caveat to keep in mind throughout: the humans did not exhaustively code
every relevant sentence in the 10-K. Some sentences counted here as
"false positives" may be genuine RAI catches the humans skipped. Treat **precision
as a lower bound** on real precision; treat **recall as AI-vs-human agreement**,
not real-world risk recall.
"""


PER_CATEGORY_EXPLAINER_MD = """
For each category we show three numbers:

- **Support** = how many sentences the human tagged with this category.
- **Precision** = of the AI's tags in this category, how often the human agreed.
- **Recall** = of the human's tags in this category, how often the AI caught it.
- Cells render `—` when the metric is undefined.
"""


CONFUSION_EXPLAINER_MD = """
Each row is what the **human** said about a sentence; each column is what the
**AI** said.

- **Diagonal cells** = both sides picked the same category. *(Agreement.)*
- **Top `none` row** = AI tagged a sentence the human did not. *(Over-tagging.)*
- **Left `none` column** = human tagged a sentence the AI ignored. *(Misses.)*
- **Other off-diagonal cells** = both sides tagged but disagreed on category.
"""


@st.cache_data(show_spinner=False)
def _cached_docs():
    return discover_docs()


@st.cache_data(show_spinner=False)
def _load_doc_shared(slug: str):
    """Load the per-doc artifacts that DON'T depend on which strategy is selected."""
    docs = _cached_docs()
    doc = next((d for d in docs if d.slug == slug), None)
    if doc is None:
        return None
    if not doc.has_ai:
        return doc, None
    text = doc.paths["txt_path"].read_text(encoding="utf-8")
    sentences = json.loads(doc.paths["sentences_path"].read_text(encoding="utf-8"))
    human_df = load_human_for_doc(slug)
    coder_names = coder_names_for_doc(human_df)
    return doc, {
        "text": text,
        "sentences": sentences,
        "coder_names": coder_names,
    }


@st.cache_data(show_spinner=False)
def _load_version_aligned(slug: str, version_id: str):
    """Load aligned.json + meta.json for one (slug, version)."""
    paths = versioned_paths_for(slug, version_id)
    aligned = json.loads(paths["aligned_path"].read_text(encoding="utf-8"))
    meta = {}
    if paths["meta_path"].exists():
        meta = json.loads(paths["meta_path"].read_text(encoding="utf-8"))
    return aligned, meta


def _doc_picker(docs) -> str | None:
    """Sidebar selectbox + status legend. Returns the selected slug."""
    if not docs:
        st.sidebar.error("No docs in registry. Did you create data/humanannotations.csv?")
        return None

    def _label(d) -> str:
        status = "🟢" if d.has_ai else ("🟡" if d.has_html else "⚪")
        return f"{status} {d.company_display} {d.year}"

    slug = st.sidebar.selectbox(
        "Document",
        options=[d.slug for d in docs],
        format_func=lambda s: _label(next(d for d in docs if d.slug == s)),
    )
    st.sidebar.caption(
        "🟢 AI run · 🟡 HTML only · ⚪ no HTML yet"
    )
    return slug


def _render_document_view(aligned, sentences, text, coder_names):
    paragraphs = build_paragraphs(text, sentences, aligned["anchor_sources"])
    ai_cards = build_cards(aligned["cards_by_anchor"], sentences, "ai")
    human_cards = build_cards(aligned["cards_by_anchor"], sentences, "human")

    counts = dict(aligned["counts"])

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("reading_view.html.j2")
    html = template.render(
        paragraphs=paragraphs,
        ai_cards=ai_cards,
        human_cards=human_cards,
        unmatched_ai=aligned["unmatched_ai"],
        unmatched_human=aligned["unmatched_human"],
        counts=counts,
        coder_a_name=coder_names.get("A", ""),
        coder_b_name=coder_names.get("B", ""),
    )

    iframe_height = max(50000, len(sentences) * 30)
    st.components.v1.html(html, height=iframe_height, scrolling=True)


def _render_all_annotations(aligned, sentences, slug):
    df_full = pd.DataFrame(build_annotations_rows(aligned, sentences))
    counts = aligned["counts"]
    a_total = counts.get("human_a_total", 0)
    b_total = counts.get("human_b_total", 0)
    st.markdown(
        f"**{len(df_full)} annotations** — "
        f"AI {counts['ai_total']} ({counts['ai_unmatched']} unmatched) · "
        f"Coder A {a_total} · Coder B {b_total} "
        f"({counts.get('human_unmatched', 0)} unmatched)"
    )

    coders = sorted({c for c in df_full["Coder"].unique() if c})
    selected = st.multiselect("Filter by source/coder", coders, default=coders)
    df = df_full[df_full["Coder"].isin(selected)] if selected else df_full

    col_filtered, col_all = st.columns([1, 1])
    with col_filtered:
        st.download_button(
            f"Download filtered ({len(df)} rows)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"{slug}_annotations_filtered.csv",
            mime="text/csv",
            disabled=len(df) == 0,
        )
    with col_all:
        st.download_button(
            f"Download all ({len(df_full)} rows)",
            data=df_full.to_csv(index=False).encode("utf-8"),
            file_name=f"{slug}_annotations_all.csv",
            mime="text/csv",
        )

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        height=min(900, 50 + 35 * len(df)),
        column_config={
            "Source": st.column_config.TextColumn("Source", width="small"),
            "Coder": st.column_config.TextColumn("Coder", width="small"),
            "Anchor ID": st.column_config.TextColumn("Anchor", width="small"),
            "Sentence": st.column_config.TextColumn("Sentence (first 120 chars)", width="large"),
            "Type": st.column_config.TextColumn("Type", width="small"),
            "Category": st.column_config.TextColumn("Category", width="medium"),
            "Subcategory": st.column_config.TextColumn("Subcategory", width="medium"),
            "Strength": st.column_config.NumberColumn(
                "Strength", help="1–3 for mitigations; blank for risks", format="%d/3", width="small"
            ),
        },
    )


def _render_evaluation(aligned, sentences, coder_names):
    taxonomy = load_taxonomy()

    st.markdown("## What we did")
    st.markdown(EVAL_INTRO_MD)

    coder_filter_options = {
        "union": "Union (any coder tagged)",
        "intersection": "Intersection (both coders agreed on category)",
        "coder_a": f"Coder A only{(' — ' + coder_names.get('A')) if coder_names.get('A') else ''}",
        "coder_b": f"Coder B only{(' — ' + coder_names.get('B')) if coder_names.get('B') else ''}",
    }
    coder_filter = st.radio(
        "Human ground truth",
        options=list(CODER_FILTERS),
        format_func=lambda k: coder_filter_options.get(k, k),
        horizontal=True,
    )

    frame = build_sentence_label_frame(aligned, sentences, taxonomy, coder_filter=coder_filter)
    all_categories = taxonomy["all_categories"]
    y_true, y_pred, label_names = build_multilabel_matrices(frame, all_categories)
    counts = aligned.get("counts", {})

    s1, s2, s3 = st.columns(3)
    s1.metric("Sentences AI tagged", counts.get("anchors_with_ai", 0))
    s2.metric("Sentences humans tagged", counts.get("anchors_with_human", 0))
    s3.metric("Sentences both tagged", counts.get("anchors_with_ai_and_human", 0))

    # Inter-coder agreement
    iaa = inter_coder_agreement(aligned, taxonomy)
    if iaa.get("kappa") is not None:
        st.markdown("## Inter-coder agreement (A vs B)")
        k = iaa["kappa"]
        st.metric(
            "Cohen's κ (per anchor × category)",
            f"{k:.2f}",
            help=(
                "Cohen's kappa over the binary 'did this coder mark this "
                f"category on this anchor' labels across {iaa['n_pairs']:,} "
                f"(anchor × category) pairs spanning {iaa['n_anchors']} anchors."
            ),
        )
        st.caption(
            f"{iaa['agreement_anchors']} of {iaa['n_anchors']} co-annotated anchors "
            f"had identical category sets across A and B."
        )

    st.markdown("## How close was AI, per category?")
    st.markdown(PER_CATEGORY_EXPLAINER_MD)
    cat_df = per_category_report(y_true, y_pred, label_names)
    st.dataframe(cat_df, hide_index=True, width="stretch")

    st.markdown("**Rolled-up summary across all categories:**")
    agg = aggregate_metrics(y_true, y_pred)
    c1, c2, c3 = st.columns(3)
    for col, name in zip([c1, c2, c3], ["weighted", "micro", "macro"]):
        p, r, f1 = agg[name]
        col.metric(
            f"{name.title()} F1",
            f"{f1:.2f}",
            help=f"precision = {p:.2f} · recall = {r:.2f}",
        )

    st.markdown("## Where did AI and humans agree and disagree?")
    st.markdown(CONFUSION_EXPLAINER_MD)
    cmat, clabels = category_confusion_matrix(frame, all_categories)
    fig_conf = px.imshow(
        cmat, x=clabels, y=clabels, text_auto=True,
        labels={"x": "AI said", "y": "Human said", "color": "sentences"},
        color_continuous_scale="Blues", aspect="auto",
    )
    fig_conf.update_xaxes(side="top", tickangle=-40)
    fig_conf.update_layout(height=620, margin=dict(l=160, t=160, r=20, b=20))
    st.plotly_chart(fig_conf, width="stretch")
    st.markdown(interpret_category_matrix(cmat, clabels))

    st.markdown("## Where is AI over-tagging?")
    fp_df = false_positive_category_counts(frame)
    if fp_df.empty:
        st.info("No AI-only sentences — nothing to plot.")
    else:
        fig_fp = px.bar(
            fp_df, x="fp_count", y="category", orientation="h",
            color="fp_count", color_continuous_scale="Reds",
            labels={"fp_count": "sentences AI tagged but human did not", "category": ""},
        )
        fig_fp.update_layout(
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig_fp, width="stretch")

    st.markdown("## Export")
    export_df = per_sentence_comparison_table(frame, all_categories)
    st.download_button(
        "Download per-sentence comparison (CSV)",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name="evaluation_per_sentence.csv",
        mime="text/csv",
    )


def _format_version(version_id: str) -> str:
    strategy = STRATEGIES.get(version_id)
    if strategy is None:
        return version_id
    return strategy.label()


def main() -> None:
    docs = _cached_docs()
    slug = _doc_picker(docs)
    if not slug:
        st.stop()

    result = _load_doc_shared(slug)
    if result is None:
        st.error(f"Slug {slug!r} not found in registry.")
        st.stop()

    doc, shared = result
    st.markdown(f"### {doc.company_display} {doc.year} 10-K")

    if not doc.has_html:
        st.warning(
            f"No HTML at `data/10ks/{doc.slug}.htm`. Drop the EDGAR filing there "
            f"and run `python -m src.pipeline --doc {doc.slug} --version baseline`."
        )
        st.stop()
    if shared is None or not doc.versions:
        st.warning(
            f"No AI versions have been built for **{doc.slug}** yet.\n\n"
            f"From the project root:\n\n"
            f"```\npython -m src.pipeline --doc {doc.slug} --version baseline\n```"
        )
        st.stop()

    version_id = st.selectbox(
        "AI methodology",
        options=list(doc.versions),
        format_func=_format_version,
        help="Each version is a different chunking / prompting strategy. Humans stay constant.",
    )
    aligned, meta = _load_version_aligned(slug, version_id)
    strategy = STRATEGIES.get(version_id)
    description = (
        (strategy.description if strategy else None)
        or meta.get("description")
        or "(no description recorded)"
    )
    with st.expander(f"About this version — {version_id}", expanded=False):
        st.markdown(description)
        details = []
        if meta.get("model"):
            details.append(f"**model:** `{meta['model']}`")
        if meta.get("chunker"):
            params_txt = ""
            if meta.get("chunker_params"):
                params_txt = " " + ", ".join(f"{k}={v}" for k, v in meta["chunker_params"].items())
            details.append(f"**chunker:** `{meta['chunker']}`{params_txt}")
        if meta.get("n_chunks") is not None:
            details.append(f"**chunks sent to LLM:** {meta['n_chunks']}")
        if meta.get("created_at"):
            details.append(f"**created at:** {meta['created_at']}")
        if details:
            st.markdown(" · ".join(details))

    coder_names = shared["coder_names"]
    with st.expander("What the cards mean", expanded=False):
        st.markdown(
            legend_for_doc(coder_names.get("A", ""), coder_names.get("B", "")),
            unsafe_allow_html=True,
        )

    doc_tab, table_tab, eval_tab = st.tabs(
        ["Document View", "All Annotations", "Evaluation"]
    )
    with doc_tab:
        _render_document_view(aligned, shared["sentences"], shared["text"], coder_names)
    with table_tab:
        _render_all_annotations(aligned, shared["sentences"], doc.slug)
    with eval_tab:
        _render_evaluation(aligned, shared["sentences"], coder_names)


main()
