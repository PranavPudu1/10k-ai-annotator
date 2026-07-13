# Mentor's framework — status per bullet

This walks the mentor's "Notes on LLM prompting experiments" doc top to
bottom and gives a direct answer under each header, keyed to the code
paths and sample outputs that back it up.

Full experiment log with numbers: [`EXPERIMENT_LOG.md`](../EXPERIMENT_LOG.md).
Interactive comparison of all versions: **Netlify** (link in main
[README.md](../README.md)).

---

## Problem setup

- **Input unit**: sentence. Emitted by [src/sentence_index.py](../src/sentence_index.py) using `pysbd`. Anchor IDs are position-based (`s-00001`, `s-00002`, …). Stored per doc at `output/{slug}/sentences.json`.
- **Output per sentence**: zero or more annotations, each with `(kind, category, subcategory, strength)`. Stored per (doc, strategy) at `output/{slug}/versions/{version_id}/ai_annotations.json`.
- **Alignment against humans**: [src/align.py](../src/align.py) matches AI sentences to human-annotated sentences by anchor; result at `output/{slug}/versions/{version_id}/aligned.json`.

---

## Units — chunk sizes given to the LM

Mentor's options: A (whole doc), B (fixed N-sentence chunks), C (keyword ± N window), D (BM25).

| Option | Status | Where |
|---|---|---|
| **A. Whole doc** | ✅ Done — this is V0 baseline | [src/chunkers.py](../src/chunkers.py) `full_doc_chunker`; V0 = strategy `baseline` |
| **B. N-sentence chunks (20, 40)** | ⏳ **Not done — deferred.** No sliding-window-by-position chunker in [src/chunkers.py](../src/chunkers.py) yet. | Would add e.g. `n_sentence_chunker(n=20, stride=20)` in [src/chunkers.py](../src/chunkers.py); register a new strategy in [src/strategies.py](../src/strategies.py) |
| **C. Keyword ± 20 sentences** | ✅ Done — V1 `keyword_window_20` (window merging) and V2 `keyword_per_sentence` (matched sentence in isolation) | [src/keyword_filter.py](../src/keyword_filter.py), [src/chunkers.py](../src/chunkers.py) `keyword_window_chunker` and `keyword_per_sentence_chunker` |
| **D. BM25 / retrieval** | ⏳ **Not done — deferred.** Explicitly labeled LATER by the mentor. | Would live alongside the keyword filter as an alternative candidate-selection module |

**Key finding on chunking**: on Alphabet 2024 the keyword+window approach (V1) is *indistinguishable* from the full-doc baseline (V0) — 54 vs 52 tags, 13 vs 12 caught. Alphabet's 10-K is so AI-dense that the ± 20 sentence windows merge into ~99% of the doc anyway. Better test on a low-AI-density doc (Tesla, Netflix) would differentiate the two.

---

## Pipeline — per input unit

Mentor's options: (1) all outputs at once, (2) sequential (kind → subcat → strength), (3) hybrid (kind → subcat+strength).

| Option | Status | Where |
|---|---|---|
| **All at once** | ✅ Done — V0, V4, V4.1 (all one-shot LLM call over the input unit) | [src/prompt_build.py](../src/prompt_build.py) `build_system_prompt` / `build_hai_tuned_prompt` |
| **Sequential (kind → cat/sub → strength)** | ✅ Done — V3, 4 phases | [src/sequential_workflow.py](../src/sequential_workflow.py) `run_sequential_batched` |
| **Sequential with additional passage-level context step** | ✅ Done — V5, 6 phases (passage identification → candidate sweep → HAI-guarded filter → kind → cat/sub → strength) | [src/sequential_passage_workflow.py](../src/sequential_passage_workflow.py) `run_sequential_passage_aware` |
| **Hybrid (kind → subcat + strength together)** | ⏳ **Not done — deferred.** V3/V5 keep strength as a separate final phase. | Would collapse V3's Phases 3+4 into one call in [src/sequential_workflow.py](../src/sequential_workflow.py) |

**Key finding on pipeline**: staging helps. V3 (sequential 4-phase) catches 20 human anchors on Alphabet 2024 vs V0's 12 — because Phase 2 drops 70% of the initial candidates as "not actually risks or mitigations," which V0's one-shot can't do. V5 ties V3 at 20 with a different miss profile (catches Legal-context misses V3 misses; loses EU AI Act sentences V3 catches).

---

## Structure — thinking / CoT tokens

Mentor's ask: `<REASONING>…</REASONING>` followed by `<ANSWER>…</ANSWER>`.

**Status**: **Effectively done for V5**, deferred for V0–V4. V5's Phase 3 verdict schema already includes a required `reason` field — every one of 205 filter verdicts on Alphabet 2024 has one, averaging 151 chars for kept sentences and 86 chars for dropped, and they cite the passage context. It's CoT-equivalent; it's just not wrapped in `<Reasoning>` XML.

Sample kept reason:
> `s-00277`: "Inside a sustainability passage, this explicitly identifies uncertainty around AI's future environmental impact as a risk consequence."

Sample dropped reason:
> `s-00110`: "This is a descriptive statement about centralized AI R&D, not a risk consequence or mitigation action."

Surfaced verbatim on the **Missed Human Tags** tab of the V5 page on Netlify.

Adding schema-wide `<Reasoning>` fields to V0/V1/V2/V4/V4.1 would be a real change (their schemas emit annotations, not verdicts) — deferred until we're actively iterating on one of those.

**We're not using a Reasoning LM.** All strategies call gpt-5.4-mini via the OpenAI SDK ([src/llm_call.py](../src/llm_call.py)). If we switch to a Reasoning model (e.g. o1 or a Claude with `thinking` enabled), saving the thinking trace would happen alongside the response cache in `llm_raw_response.json`.

---

## Outputs saved

Both requested outputs are saved per (doc, version):

- **All LLM outputs for debugging**: `output/{slug}/versions/{version_id}/llm_raw_response.json`. For single-call strategies (V0/V1/V2/V4/V4.1), this is a list of `{chunk_id, raw_response}` from OpenAI's SDK dump. For sequential strategies (V3/V5), it's a list of `{phase, raw_response}` so partial reruns work (see [src/llm_call.py](../src/llm_call.py) `call_model_per_chunk` and [src/sequential_passage_workflow.py](../src/sequential_passage_workflow.py) `_write_cache`).
- **Predicted output tags** (sentence id → tag): `output/{slug}/versions/{version_id}/ai_annotations.json` (deduped, validated) and `output/{slug}/versions/{version_id}/aligned.json` (aligned to sentence anchors + counts).
- **Strategy metadata**: `output/{slug}/versions/{version_id}/meta.json` — records `workflow`, `chunker`, `prompt_builder`, `model`, `n_chunks`, `created_at`.

---

## Evaluation — summary statistics + metrics

All in [src/evaluation.py](../src/evaluation.py) and surfaced on the Netlify **Evaluation** tab per (doc, version):

| Requested | Where |
|---|---|
| Risk vs Mitigation precision / recall / F1 | Not called out per-kind currently, but subsumed by the per-category report below. Available if we want it — filter on `kind == "Risk"` vs `"Risk Mitigation"` in [src/evaluation.py](../src/evaluation.py) `build_multilabel_matrices`. |
| Per-subcategory + macro precision / recall / F1 | `per_category_report` in [src/evaluation.py](../src/evaluation.py); `aggregate_metrics` for micro / macro / weighted. Rendered on Evaluation tab as a sortable table. |
| Strength statistics | Coverage in the Evaluation tab (min/median/max per-side) but no confusion matrix on strength alone yet — deferred. |
| Confusion matrices | `category_confusion_matrix` in [src/evaluation.py](../src/evaluation.py); rendered as Plotly heatmap on the Evaluation tab. |
| Sample errors (FP and FN examples) | New **Missed Human Tags** tab per version: lists every anchor humans tagged that the AI missed, the human tag, the sentence, and (for V3 and V5) the per-phase diagnosis of where it was lost. See [src/build_static.py](../src/build_static.py) `_build_missed_page`. |
| Thinking traces / CoT for debugging | V5's `reason` field, as above. Surfaced on the Missed page. |

Additional: **Cohen's κ** for inter-coder agreement between Coder A and Coder B (`inter_coder_agreement` in [src/evaluation.py](../src/evaluation.py)).

---

## Open question — redundancy inflation

Mentor's question: *"is it a problem that there is likely redundancy in sentences (many tagged sentences on the same point or topic will inflate the score)?"*

**Honest answer:** yes probably, and we haven't addressed it. Current deduplication is only exact-tuple: [src/normalize.py](../src/normalize.py) `dedupe_annotations` drops entries with matching `(normalized sentence text, kind, category, subcategory, strength)`. Two different sentences making the same point in different words both count separately.

**What we could do:**
- Topic-level clustering of tagged sentences per (doc, category) using embeddings, report a "distinct claims" count alongside "total tags."
- Per-category weighted recall: assign 1/N credit for a claim covered N times in the human labels.
- Simple structural dedupe: sentences that are consecutive and both tag the same (category, subcategory) get merged.

None of these are implemented. This is the one item where a decision from the mentor would help — how they want redundancy handled in the scoring will affect the choice.

---

## What is genuinely still open

- **Units option B** (arbitrary N-sentence chunks, not keyword-anchored).
- **Units option D** (BM25 / vector retrieval).
- **Pipeline hybrid** (kind → subcat + strength together in one call).
- **CoT tags for V0/V1/V2/V4/V4.1** (V5 already has it via `reason`).
- **Strength confusion matrix / statistics** as its own view.
- **Redundancy handling** — awaiting mentor guidance on the scoring philosophy.
- **CLI decomposition** (`--chunker`, `--pipeline`, `--rules`) — nice for sweeps; current `--version` presets are ergonomic enough for now.
