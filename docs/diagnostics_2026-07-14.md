# Phase 0 diagnostics — notes doc follow-up

Read-only investigation before committing to any code changes.

> **Post-fix update (2026-07-16).** This is a dated snapshot from the diagnosis phase. The recommendations for Items 3 (skip splitter fix) and 4 (defer CoT) were later reversed once the fixes proved cheap and shippable. The two-rule post-splitter merge shipped in [`src/sentence_index.py`](../src/sentence_index.py) (`_should_merge` / `_post_merge`); the three affected docs were re-indexed. XML `<Reasoning>` CoT shipped as **V6** (`xml_cot_baseline`). See [README §Problem setup](../README.md) and [§Structure — thinking tokens](../README.md) for the current status. Registry counts in Diagnostic D are also frozen at 2026-07-14 (51 docs / 57 tuples / 7 Alphabet versions); current counts are in [`EXPERIMENT_LOG.md`](../EXPERIMENT_LOG.md).

---

## Diagnostic A — Sentence fragment analysis

**Question:** are the 15 HAI-flagged "AI incorrectly breaking up sentences into fragments" cases real splitting bugs in our current pipeline?

**Method:** loaded all 16 fragment-flagged HAI records (turned out to be 16, not 15). For each, located the referenced `anchor_id` in the current `output/{slug}/sentences.json` and compared with the HAI CSV's excerpt.

**Findings:**

| Doc | Flagged | Still present as fragment | Anchor stale (points to different text) | Unmatched (not in current sentences.json) |
|---|---|---|---|---|
| alphabet_2024 | 2 | 0 | 2 | 0 |
| amazon_2024 | 3 | 1 | 0 | 2 |
| broadcom_2024 | 3 | 0 | 0 | 3 |
| meta_2024 | 1 | 1 | 0 | 0 |
| microsoft_2024 | 2 | 0 | 0 | 2 |
| nvidia_2024 | 1 | 0 | 0 | 1 |
| oracle_2024 | 3 | 1 (s-00803, dup counted 2x) | 0 | 1 |
| tesla_2024 | 1 | 0 | 0 | 1 |
| **Total** | **16** | **~3 confirmed** | **2** | **10** |

**Three confirmed present fragments** (all currently in our sentences.json):

1. `amazon_2024 s-01320`: "The Company is involved from time to time in claims, proceedings, and litigation, including the following:" — ends with colon, introduces a list.
2. `meta_2024 s-01268`: "support informed risk-based decision-making and prioritization of cybersecurity countermeasures and risk mitigation strategies." — starts with lowercase "support"; is a continuation from a preceding bullet.
3. `oracle_2024 s-00803`: "Responding to any such claim, regardless of its validity, could:" — colon-terminated list header, followed by "•" bullet marker.

**Ten unmatched anchors** — HAI reviewers flagged these against an earlier version of our sentence indexing that no longer matches. Cannot classify without re-running against those docs, but the HAI excerpts show the same pattern (mid-clause cuts, list-format artifacts).

**Root cause of confirmed fragments:** pysbd handles English abbreviations well but splits list-format text awkwardly. When a 10-K contains "X could:\n• item 1\n• item 2", pysbd creates one sentence for the colon-header and one per bullet. This is not an abbreviation-splitting bug; it's a list-format handling issue.

**Verdict:** below the "≥5 real bugs" threshold from the plan. **A splitter fix is NOT justified** by the current evidence. The 10 unmatched anchors may or may not still exist in the current pipeline; without a full re-index they're phantom flags.

**Recommendation:** document the finding, skip the splitter fix. If we want to be thorough later, a small post-processing step could merge sentences ending with ":" into the following sentence, but it isn't blocking anyone right now.

---

## Diagnostic B — Is V5's existing `reason` field CoT-quality?

**Question:** does V5's Phase 3 already emit informative reasoning per verdict, or do we need to add a separate `<Reasoning>` field?

**Method:** pulled the P3 cache from `output/alphabet_2024/versions/sequential_passage_aware/llm_raw_response.json`. Inspected the `reason` field on all 205 verdicts.

**Findings:**

- 205 total P3 verdicts (44 kept, 161 dropped).
- Every verdict has a non-empty `reason`.
- Kept-reason average length: 151 chars. Dropped-reason average length: 86 chars.
- Reasons are specific, cite the passage context, and often name the concrete drop rule that triggered.

**Sample kept reasons (V5 Phase 3):**

- s-00077: *"Inside an AI-topic passage about rising capex, this sentence describes a downstream consequence: increased infrastructure spending to support AI products and services."*
- s-00277: *"Inside a sustainability passage, this explicitly identifies uncertainty around AI's future environmental impact as a risk consequence."*
- s-00300: *"Inside a regulatory-risk passage, this identifies AI-related laws and enforcement actions as an expanding risk environment with compliance consequences."*

**Sample dropped reasons:**

- s-00106: *"This is a strategy/positioning statement that Alphabet is an AI-first company, not a risk or mitigation disclosure."*
- s-00107: *"This is generic corporate leadership context and does not describe an AI risk or mitigation."*
- s-00110: *"This is a descriptive statement about centralized AI R&D, not a risk consequence or mitigation action."*

**Verdict:** V5's `reason` field IS chain-of-thought. It's just not called `reasoning` and not wrapped in `<Reasoning>` XML. Adding another schema-wide field would be duplicate work — we already have per-verdict CoT for the strategy that actually needs it (V5).

**Recommendation:** skip the schema-wide CoT change. Do one small tweak: surface V5's existing `reason` on the Missed Human Tags page next to the diagnosis (currently already visible for P3 drops via the diagnosis line, but could be more prominent).

For V0–V4/V4.1 (single-call strategies), there's no per-sentence reason because they emit annotations, not verdicts. Adding a schema-level reasoning field to those WOULD be a real change — but they're not the strategies we're iterating on. Deferred.

---

## Diagnostic C — Comparison to Naomi's pipeline

**Question:** are we using the same pipeline as Naomi, and if not, what's different?

**Findings from reading `Responsible-AI-Based-Investment-main/`:**

Naomi's pipeline (a Colab notebook, auto-converted to `src/filter-and-upload-to-hf/xml_parsing.py`):

- **Input:** SEC EDGAR full-submission SGML files OR the Hugging Face dataset `juand-r/ai-sec-10k-filings-since-2020`.
- **Section extraction:** splits the 10-K body at Item boundaries (Item 1, 1A, 1C, 7, etc.).
- **Sentence splitter:** `re.compile(r'(?<=[.!?])\s+')` — a **plain regex** that splits on `.`, `!`, or `?` followed by whitespace. No abbreviation handling. This is more brittle than pysbd.
- **Keyword filter:** matches from `ai-keywords.txt` (~195 terms) and `privacy-keywords.txt`, keeps sentences within ±N of a hit.
- **Output:** JSONL per filing with char spans for each matched keyword; then uploaded to Hugging Face.
- **Purpose:** dataset preparation for downstream RAI research. Does NOT do risk/mitigation annotation.

Our pipeline (`src/`):

- **Input:** SEC EDGAR HTML filings via `data/fetch_10ks.py`.
- **Section extraction:** none — we process the full doc; V5 identifies AI-topic passages via LLM at annotation time.
- **Sentence splitter:** `pysbd` (Python Sentence Boundary Detector) with a moderate abbreviation-handling built in. Better than Naomi's regex.
- **Keyword filter:** the same 195-term list (we copied it), used only by V1/V2 strategies for chunking.
- **Output:** per-doc, per-version `ai_annotations.json` + `aligned.json` + evaluation metrics + Netlify static site.
- **Purpose:** actual RAI risk/mitigation tagging with side-by-side human comparison and versioned strategy experiments.

**One-line answer:** No, this is a different pipeline than Naomi's. Naomi's is a dataset-preparation script that emits keyword-filtered sentence spans as JSONL. Ours is an annotation pipeline that runs versioned LLM strategies against the same 10-Ks and produces labeled tags with precision/recall metrics against human ground truth. We reuse Naomi's keyword list (`ai-keywords.txt`), but not her sentence splitter (we use pysbd), not her SGML parser (we use HTML via BeautifulSoup), and not her output format.

---

## Diagnostic D — Experiment log feasibility

**Question:** do our existing `meta.json` + `aligned.json` files have all the columns we'd need for an experiment log?

**Findings:**

`meta.json` (per (doc, version)) contains: `id`, `display_label`, `name`, `description`, `workflow`, `chunker`, `chunker_params`, `prompt_builder`, `model`, `n_chunks`, `created_at`.

`aligned.json.counts` contains: `ai_total`, `ai_matched`, `ai_unmatched`, `anchors_with_ai`, `anchors_with_human`, `anchors_with_ai_and_human`, `human_a_total`, `human_b_total`, `human_matched`, `human_unmatched`, plus per-coder overlap counts.

**Registry state:** 51 docs, 57 total (doc, version) tuples currently on disk. Alphabet 2024 has 7 (baseline + 6 experiments); the other 50 docs have just baseline.

**Verdict:** all data is there. `EXPERIMENT_LOG.md` is a straightforward walk of `output/*/versions/*/{meta,aligned}.json` — no schema changes needed.

**Recommendation:** ship the experiment log script as-is.

---

## Summary of decisions

| Phase 1 item | Diagnostic verdict | Do it? |
|---|---|---|
| Item 1 — `EXPERIMENT_LOG.md` script | Data exists (D) | **Yes, straight-through** |
| Item 2 — `README.md` overhaul | Naomi comparison ready (C) | **Yes, straight-through** |
| Item 3 — sentence splitter fix | ~3 confirmed bugs, list-format issue not abbreviation (A) | **No — defer** |
| Item 4 — `<Reasoning>` CoT schema-wide | V5 Phase 3 already has CoT-quality `reason` (B) | **No — surface existing `reason` on Missed page instead** |
| Item 5 — draft update message | Ready | **Yes** |

**Cost of Phase 1 as scoped:** $0. No LLM re-runs needed.

**Time:** ~1.5–2 hours (script + README + tiny build_static tweak + draft reply).
