# Status against the notes doc

Reference: the "Notes on LLM prompting experiments" Google Doc (`docs.google.com/document/d/1Z3y9SuAL3ujBw8sOOr5wR8YaloadKsdivELBpYrBiBg`).

This walks that doc top-to-bottom and shows what is **done**, what is **partially done**, and what is **not done / deferred**.

Full experiment log with numbers: [`EXPERIMENT_LOG.md`](../EXPERIMENT_LOG.md). Interactive comparison of all versions: **Netlify** (link in main [README.md](../README.md)).

---

## At a glance

| Notes doc section | Status |
|---|---|
| Problem setup (input / output / labels) | ✅ Done |
| Sentence-splitting fragments (check-in follow-up) | ✅ **Done** — fixed via post-splitter merge; verified 5 ways |
| Units A — whole doc | ✅ Done (V0) |
| Units B — fixed N-sentence chunks | ✅ **Done** (V7 = 20-sentence, V8 = 40-sentence) |
| Units C — keyword ± N-sentence context | ✅ Done (V1 window + V2 per-sentence) |
| Units D — BM25 | ⏳ **Not done** — deferred (notes doc marked LATER) |
| Pipeline: all outputs at once | ✅ Done (V0, V4, V4.1, V6) |
| Pipeline: sequential (kind → cat/sub → strength) | ✅ Done (V3, V5) |
| Pipeline: hybrid (kind → cat+strength together) | ⏳ **Not done** — deferred |
| Structure: `<Reasoning>` / thinking tokens | ✅ **Done** — V6 wraps reasoning in literal `<Reasoning>…</Reasoning>`; V5 has equivalent via `reason` field |
| Outputs: LLM output logs | ✅ Done (`llm_raw_response.json` per version) |
| Outputs: predicted tags per sentence | ✅ Done (`ai_annotations.json` + `aligned.json`) |
| Evaluation: per-subcategory + macro P/R/F1 | ✅ Done |
| Evaluation: confusion matrices | ✅ Done (category matrix; strength matrix pending) |
| Evaluation: FP/FN sample examples | ✅ Done (Missed Human Tags page per version) |
| Experiment log / journal | ✅ Done (auto-generated `EXPERIMENT_LOG.md`) |
| Question: redundancy inflation | ⏳ **Open** — awaiting decision on scoring philosophy |

---

## Problem setup ✅

- **Input unit**: sentence. Emitted by [src/sentence_index.py](../src/sentence_index.py) using `pysbd`. Anchor IDs are position-based (`s-00001`, `s-00002`, …). Stored per doc at `output/{slug}/sentences.json`.
- **Output per sentence**: zero or more annotations, each with `(kind, category, subcategory, strength)`. Stored per (doc, strategy) at `output/{slug}/versions/{version_id}/ai_annotations.json`.
- **Alignment against humans**: [src/align.py](../src/align.py) matches AI sentences to human-annotated sentences by anchor; result at `output/{slug}/versions/{version_id}/aligned.json`.

---

## Units — chunk sizes given to the LM

Notes doc options: A (whole doc), B (fixed N-sentence chunks), C (keyword ± N window), D (BM25).

| Option | Status | Where |
|---|---|---|
| **A. Whole doc** | ✅ **Done** — V0 baseline | [src/chunkers.py](../src/chunkers.py) `full_doc_chunker`; strategy `baseline` |
| **B. N-sentence chunks (20, 40)** | ✅ **Done** — V7 (20-sentence chunks) and V8 (40-sentence chunks) | [src/chunkers.py](../src/chunkers.py) `n_sentence_chunker`; strategies `n_sentence_chunk_20` and `n_sentence_chunk_40` |
| **C. Keyword ± 20 sentences** | ✅ **Done** — V1 `keyword_window_20` (window merging) and V2 `keyword_per_sentence` (matched sentence in isolation) | [src/keyword_filter.py](../src/keyword_filter.py), [src/chunkers.py](../src/chunkers.py) `keyword_window_chunker` and `keyword_per_sentence_chunker` |
| **D. BM25 / retrieval** | ⏳ **Not done — deferred.** Explicitly labeled LATER in the notes doc. | Would live alongside the keyword filter as an alternative candidate-selection module |

**Key finding on chunking**: on Alphabet 2024 the keyword+window approach (V1) is *indistinguishable* from the full-doc baseline (V0) — 54 vs 52 tags, 13 vs 12 caught. Alphabet's 10-K is so AI-dense that the ± 20 sentence windows merge into ~99% of the doc anyway. A better test on a low-AI-density doc (Tesla, Netflix) would differentiate the two.

---

## Pipeline — per input unit

Notes doc options: (1) all outputs at once, (2) sequential (kind → subcat → strength), (3) hybrid (kind → subcat+strength).

| Option | Status | Where |
|---|---|---|
| **All at once** | ✅ **Done** — V0, V4, V4.1 (all one-shot LLM call over the input unit) | [src/prompt_build.py](../src/prompt_build.py) `build_system_prompt` / `build_hai_tuned_prompt` |
| **Sequential (kind → cat/sub → strength)** | ✅ **Done** — V3, 4 phases | [src/sequential_workflow.py](../src/sequential_workflow.py) `run_sequential_batched` |
| **Sequential with additional passage-level context step** | ✅ **Done** — V5, 6 phases (passage identification → candidate sweep → HAI-guarded filter → kind → cat/sub → strength) | [src/sequential_passage_workflow.py](../src/sequential_passage_workflow.py) `run_sequential_passage_aware` |
| **Hybrid (subcat + strength together)** | ⏳ **Not done — deferred.** V3/V5 keep strength as a separate final phase. | Would collapse V3's Phases 3+4 into one call in [src/sequential_workflow.py](../src/sequential_workflow.py) |

**Key finding on pipeline**: staging helps. V3 (sequential 4-phase) catches 20 human anchors on Alphabet 2024 vs V0's 12 — because Phase 2 drops 70% of the initial candidates as "not actually risks or mitigations," which V0's one-shot can't do. V5 ties V3 at 20 with a different miss profile (catches Legal-context misses V3 misses; loses EU AI Act sentences V3 catches).

---

## Structure — `<REASONING>` / thinking tokens ✅

Notes doc ask: `<REASONING>…</REASONING>` followed by `<ANSWER>…</ANSWER>`.

- **V6 (`xml_cot_baseline`)** — ✅ **new version that matches this exactly.** Same shape as V0 baseline (full doc, one LLM call) but every annotation carries a `reasoning` string wrapped in literal `<Reasoning>...</Reasoning>` XML. 73 out of 73 annotations on Alphabet 2024 have one.
- **V5 (`sequential_passage_aware`)** — ✅ CoT-equivalent via a `reason` field on every Phase 3 verdict. 205 of 205 verdicts on Alphabet 2024, averaging 151 chars for kept sentences and 86 for dropped, citing passage context. Surfaced highlighted-blue on the V5 Missed Human Tags tab. Different wrapping from V6, same debugging value.
- **V0, V1, V2, V3, V4, V4.1** — no reasoning field. Their outputs are annotations only. If we want CoT there too, the fix is straightforward — deferred since V6 already answers the question.
- **Reasoning LM** — we're using gpt-5.4-mini, not a reasoning model. If we switch to o1 or Claude with `thinking` enabled, the trace lands in `llm_raw_response.json` automatically.

Sample V6 annotation (Alphabet 2024):
> Sentence: *"We believe our approach to AI must be both bold and responsible."*
> Reasoning: `<Reasoning>The phrase "must be both bold and responsible" is a general commitment to manage AI responsibly. This is an intention-level mitigation without specific controls, so strength 1 fits.</Reasoning>`

Sample V5 kept reason:
> `s-00277`: "Inside a sustainability passage, this explicitly identifies uncertainty around AI's future environmental impact as a risk consequence."

---

## Outputs saved ✅

Both requested outputs are saved per (doc, version):

- **All LLM outputs for debugging**: `output/{slug}/versions/{version_id}/llm_raw_response.json`. For single-call strategies (V0/V1/V2/V4/V4.1), this is a list of `{chunk_id, raw_response}` from OpenAI's SDK dump. For sequential strategies (V3/V5), it's a list of `{phase, raw_response}` so partial reruns work (see [src/llm_call.py](../src/llm_call.py) `call_model_per_chunk` and [src/sequential_passage_workflow.py](../src/sequential_passage_workflow.py) `_write_cache`).
- **Predicted output tags** (sentence id → tag): `output/{slug}/versions/{version_id}/ai_annotations.json` (deduped, validated) and `output/{slug}/versions/{version_id}/aligned.json` (aligned to sentence anchors + counts).
- **Strategy metadata**: `output/{slug}/versions/{version_id}/meta.json` — records `workflow`, `chunker`, `prompt_builder`, `model`, `n_chunks`, `created_at`.

---

## Evaluation — summary statistics + metrics

All in [src/evaluation.py](../src/evaluation.py) and surfaced on the Netlify **Evaluation** tab per (doc, version):

| Requested | Status | Where |
|---|---|---|
| Risk vs Mitigation precision / recall / F1 | 🟡 subsumed by per-category, not a dedicated view | Filter on `kind` in [src/evaluation.py](../src/evaluation.py) `build_multilabel_matrices` |
| Per-subcategory + macro precision / recall / F1 | ✅ | `per_category_report` + `aggregate_metrics` |
| Strength statistics | 🟡 min/median/max coverage but no dedicated confusion matrix | Coverage in Evaluation tab; strength matrix deferred |
| Confusion matrices (category) | ✅ Plotly heatmap | `category_confusion_matrix` |
| Sample errors (FP / FN examples) | ✅ **Missed Human Tags** tab per version — lists every anchor humans tagged that the AI missed, the human tag, the sentence, and (for V3 and V5) the per-phase diagnosis of where it was lost | [src/build_static.py](../src/build_static.py) `_build_missed_page` |
| Thinking traces / CoT for debugging | ✅ for V5 (see above), 🟡 for others | V5's `reason` field, surfaced on the Missed page |

Additional: **Cohen's κ** for inter-coder agreement between Coder A and Coder B (`inter_coder_agreement` in [src/evaluation.py](../src/evaluation.py)).

---

## Open question — redundancy inflation ⏳

Notes doc: *"is it a problem that there is likely redundancy in sentences (many tagged sentences on the same point or topic will inflate the score)?"*

**Honest status:** yes probably, and we haven't addressed it. Current deduplication is only exact-tuple: [src/normalize.py](../src/normalize.py) `dedupe_annotations` drops entries with matching `(normalized sentence text, kind, category, subcategory, strength)`. Two different sentences making the same point in different words both count separately.

**Options we haven't picked:**
- Topic-level clustering of tagged sentences per (doc, category) using embeddings, report a "distinct claims" count alongside "total tags."
- Per-category weighted recall: assign 1/N credit for a claim covered N times in the human labels.
- Simple structural dedupe: consecutive sentences that both tag the same (category, subcategory) get merged.

None of these are implemented. **Awaiting a decision on the scoring philosophy** before committing to one.

---

## Consolidated "what's still open"

- **Units option B** (arbitrary N-sentence chunks, not keyword-anchored).
- **Units option D** (BM25 / vector retrieval).
- **Pipeline hybrid** (kind → subcat + strength together in one call).
- **`<Reasoning>` schema field for V0/V1/V2/V4/V4.1** (V5 already has it via `reason`).
- **Strength confusion matrix / dedicated view.**
- **Redundancy handling** — decision needed.
- **CLI decomposition** (`--chunker`, `--pipeline`, `--rules`) — nice for sweeps; current `--version` presets are ergonomic enough for now.
