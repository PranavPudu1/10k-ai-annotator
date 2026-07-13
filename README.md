# 10-K RAI Annotator

A versioned pipeline for automatic Responsible-AI risk/mitigation tagging of SEC 10-K filings, with side-by-side comparison against human annotators.

**Live site (Netlify):** https://warm-sawine-c7631b.netlify.app — browse 7 strategies applied to Alphabet 2024 without cloning anything.

## What this is

Input: a 10-K filing (HTML from EDGAR).
Output: for every sentence, zero or more labels of the form (**kind** ∈ {Risk, Risk Mitigation}, **category**, **subcategory**, **strength**).

The interesting part is that we do this **seven different ways** and compare against the same human ground truth. See the results table below.

## Quickstart

```bash
pip install -r requirements.txt
python3 -m src.pipeline --doc apple_2024 --version baseline
streamlit run src/app.py
```

The Streamlit app has a dropdown to pick any doc and any strategy version, then shows Document View / All Annotations / Evaluation / Missed Human Tags tabs.

## Strategies at a glance (V0 → V5)

Full comparison on Alphabet 2024 — 38 human anchors (+ 4 unmatched-alignment):

| Version | Method | AI tags | Anchors caught | Anchors missed |
|---|---|---:|---:|---:|
| **V0** baseline | Full doc → one LLM call | 52 | 12 | 30 |
| **V1** keyword_window_20 | Keyword filter + ±20 sentence window per hit | 54 | 13 | 29 |
| **V2** keyword_per_sentence | Keyword filter + matched sentence alone (no context) | 166 | 26 | 16 |
| **V3** sequential_batched | 4-phase LLM chain: candidate → kind → cat/sub → strength | 55 | 20 | 22 |
| **V4** hai_tuned_oneshot | Baseline + prompt tuned on HAI reviewer feedback (v1 rules) | 43 | 14 | 28 |
| **V4.1** hai_tuned_oneshot_v2 | V4 with v2 deep-read principles (15 rules from 844-record read) | 42 | 14 | 28 |
| **V5** sequential_passage_aware | 6-phase chain with passage-level context + HAI v3 guardrails | 51 | 20 | 22 |

**Full auto-generated log:** [EXPERIMENT_LOG.md](EXPERIMENT_LOG.md).

## Mentor's question mapping

If you're reading this because you sent the "Notes on LLM prompting experiments" doc: [docs/mentor_framework_mapping.md](docs/mentor_framework_mapping.md) walks your document top-to-bottom with direct answers under each header (Units, Pipeline, Structure, Outputs, Evaluation, Open Questions).

## Is this Naomi's pipeline?

Short answer: no, but it shares foundations. Full answer with side-by-side comparison: [docs/vs_naomi.md](docs/vs_naomi.md).

## Repo layout

```
10ktest/
├── src/                       LLM annotator pipeline
│   ├── strategies.py            registry of V0–V5 strategies (add new ones here)
│   ├── chunkers.py              full_doc, keyword_window, keyword_per_sentence
│   ├── keyword_filter.py        loads data/ai_keywords.txt + finds matches
│   ├── sequential_workflow.py   V3's 4-phase chain
│   ├── sequential_passage_workflow.py   V5's 6-phase chain
│   ├── prompt_build.py          baseline + HAI-tuned prompt builders
│   ├── llm_call.py              OpenAI SDK wrapper + per-chunk caching
│   ├── html_extract.py          EDGAR HTML → clean text
│   ├── sentence_index.py        pysbd sentence splitter
│   ├── align.py                 AI+human → sentence-anchored aligned.json
│   ├── evaluation.py            precision/recall/F1, confusion matrix, kappa
│   ├── pipeline.py              CLI: python -m src.pipeline --doc X --version Y
│   ├── app.py                   Streamlit interactive comparison
│   ├── build_static.py          static Netlify build
│   ├── build_experiment_log.py  regenerates EXPERIMENT_LOG.md
│   └── multi_human_csv.py       loads humanannotations.csv (Coder A + B)
├── data/
│   ├── ai_keywords.txt          195 AI-related terms (copied from Naomi's repo)
│   ├── humanannotations.csv     human ground truth (Naomi + Chibudom)
│   ├── hai_dont_rules_v1.md     rules distilled from HAI reviewer feedback (V4)
│   ├── hai_dont_rules_v2.md     v2 deep-read principles (V4.1)
│   ├── hai_dont_rules_v3.md     v3 passage-aware principles (V5)
│   ├── humanannotations.csv     resolved human tags
│   └── RAI Finance Pilot Information - *.csv    taxonomy definitions
├── output/{slug}/versions/{version_id}/
│   ├── meta.json                strategy config + timestamp
│   ├── llm_raw_response.json    raw LLM output for debugging (per-phase for V3/V5)
│   ├── ai_annotations.json      validated + deduped annotations
│   └── aligned.json             AI+human sentence-anchored comparison + counts
├── docs/
│   ├── mentor_framework_mapping.md
│   ├── vs_naomi.md
│   └── diagnostics_2026-07-14.md
├── EXPERIMENT_LOG.md            auto-generated
├── annotation_tool/             separate — Flask app for human annotators (eats Naomi's sections.jsonl)
├── dist/                        Netlify static build
└── README.md
```

## How to add a new experiment (V6+)

1. Register a new strategy in [src/strategies.py](src/strategies.py) — set `id`, `display_label`, `chunker`, `workflow`, `prompt_builder`.
2. If it needs a new chunker, add a function to [src/chunkers.py](src/chunkers.py).
3. If it needs a new multi-phase workflow, add a `run_*` function in a new `src/*_workflow.py` and wire it into [src/pipeline.py](src/pipeline.py) `run_for` alongside `sequential` and `sequential_passage_aware`.
4. Run: `python3 -m src.pipeline --doc alphabet_2024 --version {new_id}`.
5. Rebuild the site: `python3 -m src.build_static` and drop `dist/` in Netlify.

The Streamlit dropdown and Netlify per-doc landing pick up new versions automatically — no UI code changes needed.

## Outputs by version (per doc)

- `output/{slug}/text.txt` — extracted plain text (shared across strategies)
- `output/{slug}/sentences.json` — sentence index (shared)
- `output/{slug}/versions/{version_id}/meta.json` — strategy config
- `output/{slug}/versions/{version_id}/llm_raw_response.json` — raw LLM output; for V3/V5 this is per-phase for partial reruns
- `output/{slug}/versions/{version_id}/ai_annotations.json` — validated annotations
- `output/{slug}/versions/{version_id}/aligned.json` — AI+human comparison + counts

## Evaluation surfaces

- **Netlify site** (link at top): Document View, All Annotations, Evaluation, Missed Human Tags per (doc, version)
- **Streamlit** (`streamlit run src/app.py`): same four tabs, with dropdowns for doc + version + human ground truth mode (Union / Intersection / Coder A / Coder B)
- **Programmatic**: `src.evaluation` module — `per_category_report`, `aggregate_metrics`, `category_confusion_matrix`, `inter_coder_agreement` (Cohen's κ)

## Model

`gpt-5.4-mini` via OpenAI SDK. Change in [src/config.py](src/config.py). Requires `OPENAI_API_KEY` in `.env.local` at repo root.

## Diagnostics

For status on the mentor's specific asks (sentence-splitting bugs, CoT for debugging, whether this is Naomi's pipeline): [docs/diagnostics_2026-07-14.md](docs/diagnostics_2026-07-14.md).
