# 10-K RAI Annotator

A versioned pipeline for automatic Responsible-AI risk/mitigation tagging of SEC 10-K filings, with side-by-side comparison against human annotators.

- **Live comparison site (Netlify):** https://warm-sawine-c7631b.netlify.app — 7 strategies (V0–V5) applied to Alphabet 2024, browsable without cloning.
- **Reference doc I'm responding to below:** the "Notes on LLM prompting experiments" [Google Doc](https://docs.google.com/document/d/1Z3y9SuAL3ujBw8sOOr5wR8YaloadKsdivELBpYrBiBg).

This README walks that doc top-to-bottom. Each section quotes it verbatim, then answers where things stand.

**Jump to:**
- [Done so far](#done-so-far) · [Experimental log](#need-an-experimental-log--journal) · [Problem setup](#problem-setup) · [Goals](#goals) · [Redundancy question](#question-redundancy)
- [Prompt instruction](#prompt-instruction) · [Units A/B/C/D](#units-chunk-input-sizes) · [Pipeline](#pipeline-for-each-input-unit) · [Structure — CoT](#structure-thinking-tokens) · [Outputs](#outputs) · [Evaluation](#evaluation-summary-statistics)
- [Experiment tracking format](#follow-up-experiment-tracking-format) · [CLI flags for units/pipelines](#follow-up-cli-flags-for-units-and-pipelines) · [How to run it yourself](#follow-up-how-to-run-it-yourself) · [Comparison with Naomi](#follow-up-is-this-naomis-pipeline)

---

## Done so far

> **Done so far:** Prompt with entire 10k as context. Prompt iteration.

We're seven versions in now, all versioned and browsable on the [live site](https://warm-sawine-c7631b.netlify.app). Numbers on Alphabet 2024 (38 human anchors + 4 unmatched):

| Version | Method | AI tags | Anchors caught | Anchors missed |
|---|---|---:|---:|---:|
| V0 baseline | Full doc → one LLM call | 52 | 12 | 30 |
| V1 keyword_window_20 | Keyword filter + ±20 sentence window | 54 | 13 | 29 |
| V2 keyword_per_sentence | Keyword filter + matched sentence alone | 166 | 26 | 16 |
| V3 sequential_batched | 4-phase LLM chain | 55 | 20 | 22 |
| V4 hai_tuned_oneshot | Baseline + HAI-derived prompt rules (v1) | 43 | 14 | 28 |
| V4.1 hai_tuned_oneshot_v2 | v2 deep-read principles (15 rules from 844 records) | 42 | 14 | 28 |
| **V5** sequential_passage_aware | 6-phase chain + passage-level context + HAI v3 | 51 | **20** | 22 |

V3 and V5 tie at the top on human overlap. V4/V4.1 are the most conservative. V2 has the highest raw recall but 3× over-tagging.

See [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md) for the full auto-generated log across all 57 (doc, version) runs, and [`docs/notes_doc_mapping.md`](docs/notes_doc_mapping.md) for the same info as a status table.

---

## Need — an experimental log / journal

> **Need:** Experimental log/journal of things tried, and summary statistics (also include reports/data that you processed).

Done. It's at [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md), auto-generated from every version's `meta.json` + `aligned.json` — one row per (doc, version) with workflow, chunker, prompt rules, model, tag counts, catch/miss numbers, and timestamp. Regenerate any time with `python3 -m src.build_experiment_log`. If you'd rather see it in a Google Sheet or Notion I can mirror it — the source is markdown so it copy-pastes cleanly.

The "reports/data that you processed" part: the actual HAI reviewer verdicts I processed to derive the v1/v2/v3 prompt rules live in [`hai-annotations/`](hai-annotations/), and my analysis lives in [`docs/diagnostics_2026-07-14.md`](docs/diagnostics_2026-07-14.md) (fragment-flag categorization, `reason`-field sample, Naomi comparison, log feasibility).

---

## Problem setup

> **Problem setup:** Input: sentences. Output: label for each sentence where label is (risk/mitigation, subcategory, strength).

Yes, exactly this. Sentences come from `pysbd` on the extracted 10-K text ([src/sentence_index.py](src/sentence_index.py)); the label space is the RAI taxonomy in [`data/RAI Finance Pilot Information - 1. To Prompt LLM-taxonomy.csv`](data/); every output annotation is `(kind ∈ {Risk, Risk Mitigation}, category, subcategory, strength)` stored as JSON at `output/{slug}/versions/{version_id}/ai_annotations.json`.

---

## Goals

> **Goals:** Automatic tagging should be accurate: minimize false positives and false negatives. We also want to keep the cost and time reasonable. (Optional, but useful) human-understandable explanations for why things got tagged a certain way.

Where we are on each:

- **Accuracy:** best current recall against humans is 20/38 (V3 and V5), best precision-adjacent is V4.1 (42 tags, 14 caught). V2 gets to 26/38 but at 3× over-tag cost. None of these is amazing yet — the biggest remaining miss category is Legal/Uncertainty & Complexity, where humans tag sentences whose AI relevance comes from *surrounding* paragraphs.
- **Cost and time:** V5 costs about $0.05 per doc and finishes in ~30 seconds. Everything except V2 (which does 587 sentence-by-sentence calls) is cheap.
- **Explanations:** V5 emits a per-verdict `reason` field on its Phase 3 filter — every drop or keep is justified in prose. See the [Structure section](#structure-thinking-tokens) for a sample.

---

## Question — redundancy

> **Questions (unresolved):** is it a problem that there is likely redundancy in sentences (many tagged sentences on the same point or topic will inflate the score)

Honestly, yes, and we haven't solved it. Right now [`src/normalize.py`](src/normalize.py) `dedupe_annotations` only drops exact `(sentence, kind, category, subcategory, strength)` duplicates. Two sentences saying the same thing in different words still both count. Three options I've thought about, none implemented:

1. Semantic clustering per (doc, category) via embeddings — report a "distinct claims" number alongside "total tags."
2. Per-category weighted recall — 1/N credit for a claim covered N times in the humans.
3. Structural dedupe — consecutive sentences with the same (category, subcategory) get merged.

Would love a steer on the scoring philosophy before I commit to one.

---

## Prompt instruction

> **Prompt instruction:** Instructions can start with what the human annotators get. Iterate on the instruction based on the errors seen. Sometimes instructions are hard for LLMs to follow. Examples can help (but try to balance them between the different categories).

Doing this. Naomi and Angie reviewed the baseline (V0) output and produced 876 verdicts — "AI-flagged incorrectly" or "Human Miss" — with free-text reasoning per row (in [`hai-annotations/`](hai-annotations/)). I distilled those into three iterations of prompt rules:

- **v1** rules ([`data/hai_dont_rules.md`](data/hai_dont_rules.md)) — 12 hand-distilled DON'T rules from the short-label distribution. Used by V4.
- **v2** rules ([`data/hai_dont_rules_v2.md`](data/hai_dont_rules_v2.md)) — 15 principles from a systematic read of all 844 long-form reviewer explanations. Used by V4.1.
- **v3** rules ([`data/hai_dont_rules_v3.md`](data/hai_dont_rules_v3.md)) — v2 minus the strict "AI must be in the adjacent paragraph" rule, plus passage-aware guidance. Used by V5.

On few-shot examples: I sampled 4–6 real "AI-flagged incorrectly" and 2–3 "Human Miss" cases per prompt rev, balancing across categories. See [`src/hai_feedback.py`](src/hai_feedback.py) `select_few_shot_examples`.

---

## Units — chunk input sizes

### A. Entire document

> **A) Entire document (done, I think this will be a weak baseline)**

Done as V0. And yes, weak baseline — 12/38 caught, over-tagging is the failure mode. This is the reference point everything else is measured against. Code in [src/chunkers.py](src/chunkers.py) `full_doc_chunker`.

### B. Split doc into chunks (N-sentence)

> **B) Split doc into chunks (e.g., N sentence chunks, maybe try 20, 40) – ask it to tag everything inside.**

**Not done — deferred.** We don't yet have an arbitrary-position sliding-window chunker. Would live as a new function in [src/chunkers.py](src/chunkers.py) (e.g. `n_sentence_chunker(n=20, stride=20)`), a new strategy in [src/strategies.py](src/strategies.py), and that's it. Happy to build it if it's the next thing you want to see.

### C. Keyword ±20 sentence context

> **C) For each sentence containing an AI keyword(s), take the 20 sentences before and after (mirroring what our annotators are doing), and ask the LM to annotate only that sentence (in context).**

Done as two variants:

- **V1 `keyword_window_20`** — keyword filter + ±20 sentence window, overlapping windows merged. Code in [src/chunkers.py](src/chunkers.py) `keyword_window_chunker`.
- **V2 `keyword_per_sentence`** — same keyword filter but only the matched sentence is sent to the LLM, no neighbors. Tests the "no context" extreme; over-tags hard.

Real finding on V1: on Alphabet 2024 the ±20 windows merge into ~99% of the doc anyway (Alphabet is that AI-dense), so V1's results are indistinguishable from V0 baseline. A better test would be on a low-AI-density doc like Tesla or Netflix.

### D. BM25

> **D) (LATER) If we need to go beyond this keyword approach, we could try BM25.**

Explicitly LATER in the notes doc, and it's still LATER for us — not started.

---

## Pipeline — for each input unit

> **Pipeline: for each input unit — Prompt for all outputs all at once (task vs mitigation, subcategory, strength) — Prompt sequentially: 1) Prompt for task vs mitigation → 2) depending on answer prompt for subcategory (prompt is different for risk & mitigation) → 3) prompt for strength — Perhaps if strength is something that should be decided at the same time as the subcategory, we could try: 1) task vs mitigation → 2) subcategory+strength**

- **All at once** — V0, V4, V4.1. One prompt, one call, all fields at once. Code in [src/prompt_build.py](src/prompt_build.py).
- **Sequential (kind → cat/sub → strength)** — V3. Four phases exactly matching your (1)(2)(3). Code in [src/sequential_workflow.py](src/sequential_workflow.py) `run_sequential_batched`. Phase 2 drops ~70% of Phase 1's candidates as "not actually a risk or mitigation" — that's the precision boost that lifts recall from V0's 12 to V3's 20.
- **Sequential + passage-level context step** — V5. Six phases: passage identification → candidate sweep → HAI-guarded filter → kind → cat/sub → strength. Code in [src/sequential_passage_workflow.py](src/sequential_passage_workflow.py) `run_sequential_passage_aware`. The passage step is my answer to the "sentence looks generic in isolation but is inside a clearly AI-focused paragraph" problem.
- **Hybrid (subcat + strength together)** — **not done, deferred.** V3 keeps strength as a separate final phase. Easy to fold Phase 3 + Phase 4 together if we want to try it.

> **Note: an advantage of pipeline approach is it can be easier for LLMs to follow more specific instructions, one at a time, rather than multiple instructions at once.**

Confirmed empirically. V3 (sequential) beats V0 (one-shot) on the same doc by 8 anchors caught (20 vs 12). The staging genuinely helps.

---

## Structure — thinking tokens

> **Structure: Should try asking for thinking tokens, i.e., in `<REASONING> … </REASONING>`, followed by `<ANSWER> </ANSWER>` (Goal: better accuracy, and tool for debugging). If using a Reasoning LM, can also report the thinking trace (or summary, depends on the model).**

V5 already has this (with different framing). Its Phase 3 verdict schema requires a `reason` string on every keep/drop decision. On Alphabet 2024 all 205 verdicts have one, averaging 151 chars for kept sentences and 86 chars for dropped. They cite the actual passage context.

Real V5 sample (`s-00277`, dropped by Phase 3):
> "Inside a sustainability passage, this explicitly identifies uncertainty around AI's future environmental impact as a risk consequence."

Real V5 sample (`s-00110`, dropped):
> "This is a descriptive statement about centralized AI R&D, not a risk consequence or mitigation action."

The reason field is CoT-equivalent — just not wrapped in `<Reasoning>` XML. It's surfaced verbatim, highlighted in blue, on the **Missed Human Tags** tab of the V5 page on Netlify.

**V0/V1/V2/V4/V4.1 don't have this.** Their schemas emit annotations directly, no per-annotation reason. Adding a `reasoning` field to those is a real change I've deferred — happy to do it if you want the CoT everywhere.

**Reasoning LM:** we call `gpt-5.4-mini` via the OpenAI SDK, no built-in thinking trace. If we switch to a Reasoning model like o1 or Claude with `thinking` enabled, the trace lands in the same `llm_raw_response.json` cache alongside the response.

---

## Outputs

> **Outputs: Save — All LLM outputs in a log (for debugging or analysis purposes later) — The predicted output tags (sentence id → tag)**

Both saved, per (doc, version), at `output/{slug}/versions/{version_id}/`:

- `llm_raw_response.json` — the raw LLM output. For single-call strategies (V0/V1/V2/V4/V4.1) it's a list of `{chunk_id, raw_response}` from OpenAI's SDK dump. For sequential strategies (V3/V5) it's a list of `{phase, raw_response}` so I can rerun individual phases without re-billing the others.
- `ai_annotations.json` — the validated, deduped annotations (this is the "sentence id → tag" file).
- `aligned.json` — same annotations aligned to sentence anchors + human comparison + counts.
- `meta.json` — strategy config + timestamp so `EXPERIMENT_LOG.md` can auto-generate.

---

## Evaluation — summary statistics

> **Evaluation – Summary statistics/metrics: Precision and Recall — Risk vs Mitigation: precision, recall, F1 — All subcategories (for now, separately per subcategory), as well as macro-{precision, recall, F1} — Strength statistics — Confusion matrices (risk vs mitigation, subcategories, strength) — Sample examples (examples of errors for each category; false positives and false negatives). Thinking traces/CoT will also help debugging and iterating the prompt or prompting approach.**

Coverage:

- **Per-subcategory + macro precision/recall/F1** — done. [src/evaluation.py](src/evaluation.py) `per_category_report` and `aggregate_metrics` (micro/macro/weighted). Rendered as sortable tables on the Netlify **Evaluation** tab per (doc, version).
- **Category confusion matrix** — done. `category_confusion_matrix` in [src/evaluation.py](src/evaluation.py), Plotly heatmap on the Evaluation tab.
- **Sample errors (FP/FN)** — done, this is the **Missed Human Tags** tab per version. Every human-tagged sentence the AI missed, with the human tag and (for V3/V5) a per-phase diagnosis of where the AI lost it. Sequential strategies also show the V5 Phase 3 `reason` field inline as CoT.
- **Risk vs Mitigation P/R/F1 as a dedicated view** — 🟡 subsumed by the per-category report but not called out separately. Trivial to add if useful.
- **Strength statistics + confusion matrix** — 🟡 partial. We surface min/median/max strength coverage on the Evaluation tab; no dedicated strength confusion matrix yet.
- **Inter-coder agreement** — bonus, not in the notes doc. `inter_coder_agreement` in [src/evaluation.py](src/evaluation.py) computes Cohen's κ between Coder A and Coder B.

---

## Follow-up: experiment tracking format

> **Please make a new tab (or use Google Sheets, or Notion, or some other way if you have a workflow you like) to track experiments and results — so we have a record to track what was tried and how it went.**

The auto-generated markdown log at [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md) is the record. It's regenerated any time we run new experiments with `python3 -m src.build_experiment_log`. The columns are: version, workflow, chunker (+ params), prompt rules, model, AI tags, anchors caught, anchors missed, created_at.

If a Google Sheet or Notion table works better for you, the source-of-truth markdown copy-pastes into either cleanly — happy to set that up if you'd prefer that surface.

---

## Follow-up: CLI flags for units and pipelines

> **Ideally changing units and pipeline approaches etc can be done with command line flags so it's easy to run and track.**

Honest status: partially there. Today the CLI is:

```
python3 -m src.pipeline --doc alphabet_2024 --version sequential_passage_aware
```

Where `--version` is a **preset** that bundles chunker + workflow + prompt rules. The seven presets today are V0–V5 (labels in [src/strategies.py](src/strategies.py)). This is good for reproducibility, but it's *not* what the notes doc is asking for — you can't mix and match "keyword window chunker + sequential pipeline + v3 rules" without adding a new strategy.

**What decomposition would look like:**

```
python3 -m src.pipeline --doc alphabet_2024 --chunker keyword_window --pipeline sequential --rules v3
```

This is P1 work — not blocking, but the right next move if you want to sweep experiments. The refactor is bounded: split [src/strategies.py](src/strategies.py) into a chunker registry, a workflow registry, and a rules registry, and let the CLI compose them.

---

## Follow-up: how to run it yourself

> **In addition, we also want to make it easy for him to run as well.**

Full walkthrough to reproduce V5 on Alphabet 2024:

```bash
# 1. Clone
git clone https://github.com/PranavPudu1/10k-ai-annotator
cd 10k-ai-annotator

# 2. Install
pip install -r requirements.txt

# 3. Add your API key
cp .env.local.example .env.local
# then edit .env.local and paste your key

# 4. Run V5 on Alphabet 2024 (uses cached HTML + sentences in output/)
python3 -m src.pipeline --doc alphabet_2024 --version sequential_passage_aware

# 5. See the results
streamlit run src/app.py
# — or —
python3 -m src.build_static
# then open dist/alphabet_2024/sequential_passage_aware/index.html
```

Costs about $0.05, takes about 30 seconds. If you want to skip that and just look at the outputs we already ran, they're checked in at [`output/alphabet_2024/versions/`](output/alphabet_2024/versions/) — all 7 versions with their full LLM caches.

To run a different version, swap `sequential_passage_aware` for one of: `baseline`, `keyword_window_20`, `keyword_per_sentence`, `sequential_batched`, `hai_tuned_oneshot`, `hai_tuned_oneshot_v2`.

---

## Follow-up: is this Naomi's pipeline?

> **Also, could you share the code you are using? I wasn't sure if you were using the same pipeline as Naomi or not.**

You're looking at it. And no — not exactly Naomi's pipeline, but it shares foundations. Same AI-keywords list (literally copied from her `filter-and-upload-to-hf/ai-keywords.txt`), same taxonomy CSVs, same keyword-window chunking concept (that's V1). What's different: we ingest EDGAR HTML directly (not her SGML), use `pysbd` instead of her regex splitter (documented in [`annotation_tool/SEGMENTER_DECISION.md`](annotation_tool/SEGMENTER_DECISION.md) if you want the details), and go all the way downstream to LLM annotation + evaluation.

Full side-by-side in [`docs/vs_naomi.md`](docs/vs_naomi.md).

---

## Repo layout

```
10k-ai-annotator/
├── src/                       LLM annotator pipeline
│   ├── strategies.py            registry of V0–V5 (add new ones here)
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
│   ├── humanannotations.csv     human ground truth (Coder A + B)
│   ├── hai_dont_rules_v1.md     rules distilled from HAI reviewer feedback (V4)
│   ├── hai_dont_rules_v2.md     v2 deep-read principles (V4.1)
│   ├── hai_dont_rules_v3.md     v3 passage-aware principles (V5)
│   └── RAI Finance Pilot Information - *.csv    taxonomy definitions
├── output/{slug}/versions/{version_id}/
│   ├── meta.json                strategy config + timestamp
│   ├── llm_raw_response.json    raw LLM output (per-phase for V3/V5)
│   ├── ai_annotations.json      validated + deduped annotations
│   └── aligned.json             AI+human sentence-anchored comparison + counts
├── docs/
│   ├── notes_doc_mapping.md     status-per-bullet against the notes doc
│   ├── vs_naomi.md              side-by-side comparison to Naomi's pipeline
│   └── diagnostics_2026-07-14.md  Phase 0 findings on 4 specific asks
├── EXPERIMENT_LOG.md            auto-generated
└── README.md                    this file
```

## How to add a new experiment (V6+)

1. Register a new strategy in [src/strategies.py](src/strategies.py) — set `id`, `display_label`, `chunker`, `workflow`, `prompt_builder`.
2. If it needs a new chunker, add a function to [src/chunkers.py](src/chunkers.py).
3. If it needs a new multi-phase workflow, add a `run_*` function in a new `src/*_workflow.py` and wire it into [src/pipeline.py](src/pipeline.py) `run_for`.
4. Run: `python3 -m src.pipeline --doc alphabet_2024 --version {new_id}`.
5. Rebuild the site: `python3 -m src.build_static`.

The Streamlit dropdown and Netlify per-doc landing pick up new versions automatically.
