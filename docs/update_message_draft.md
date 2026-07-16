# Draft update message

Copy-paste this into Slack/email. Fill in the recipient's name and adjust tone as needed.

---

Hi [Name],

Great timing — I have a good update. I've been running the automated tagging experiments and just packaged everything up. Answering your priorities in order:

**Code:** https://github.com/PranavPudu1/10k-ai-annotator (private — happy to add you as a collaborator; send me your GitHub handle). The README has a quickstart and a link to a live Netlify site where you can browse all of the experiments without cloning anything.

**Is this Naomi's pipeline?** No, but it shares foundations — same AI-keywords list, same taxonomy, same keyword-window chunking concept. Full comparison at `docs/vs_naomi.md`. TL;DR: (1) the LLM annotator (`src/`) ingests EDGAR HTML directly (not Naomi's SGML) and runs 10 versioned strategies (V0–V8); (2) our separate human annotation Flask app (`annotation_tool/`) eats her `sections.jsonl` output verbatim. Sentence splitter is upgraded from her regex to `pysbd` in both — deliberate call documented in `annotation_tool/SEGMENTER_DECISION.md`.

**Sentence-splitting fragments — was this fixed? Yes.** Diagnosed all 16 HAI-flagged fragment cases: 3 were real fragments still present (list-header colons + lowercase-continuation bullets in `amazon_2024`, `meta_2024`, `oracle_2024`); the other 13 pointed at anchor IDs from an older index. Shipped a two-rule post-splitter merge pass in [`src/sentence_index.py`](../src/sentence_index.py) (`_should_merge` / `_post_merge`) and re-indexed the 3 affected docs. Verified with inline unit tests, regression on clean 10-K prose (decimals, `Ph.D.`, `EU AI Act`, section numbers all still split correctly), and a 5-doc sanity check (2.7–3.8% sentence-count drop, no colon-ended sentences or lowercase-started ones in the first 100). Full diagnostic + post-fix note in [`docs/diagnostics_2026-07-14.md`](diagnostics_2026-07-14.md).

**Chain-of-thought / reasoning traces:** shipped a new version — **V6 (`xml_cot_baseline`)** — that implements the literal `<Reasoning>…</Reasoning>` XML format per annotation. 73/73 annotations on Alphabet 2024 are wrapped. V5 already had CoT-equivalent output via its per-verdict `reason` field on Phase 3 (~151 chars avg, cites passage context, rendered blue on V5's Missed page). V0/V1/V2/V3/V4/V4.1 don't have reasoning fields — deferred until we're iterating on one of those.

**Prompt iteration on the two error modes (over-tagging non-RAI + missing context):** empirical answer — measurably yes, not fully.
- **Over-tagging non-RAI:** AI tag count on Alphabet 2024 drops as rules get more specific: V0 = 52 → V4 = 43 → V4.1 = 42 (a ~19% reduction while lifting recall).
- **Missing context:** anchors caught climbs from V0 = 12 → V3 = 20 → V5 = 20 (V3/V5 catch different 20s; combined coverage would be 24). Sequential staging is the driver.
- **Residual:** Legal-context sentences where the sentence doesn't say "AI" are the dominant remaining miss category.

**Units + Pipeline (your options A/B/C/D + all-at-once/sequential):**

| Units | Status |
|---|---|
| A. Whole doc | ✅ V0 baseline |
| B. Fixed N-sentence chunks (20, 40) | ✅ **V7** (20-sentence, 26 caught) + **V8** (40-sentence, 21 caught) |
| C. Keyword ± N window | ✅ V1 (window merging) + V2 (per-sentence isolation) |
| D. BM25 | ⏳ Deferred (you marked LATER) |

| Pipeline | Status |
|---|---|
| All at once | ✅ V0, V4, V4.1, V6, V7, V8 |
| Sequential (kind → cat/sub → strength) | ✅ V3 (4 phases) |
| Sequential + passage-level context step | ✅ V5 (6 phases) |
| Hybrid (kind → cat/sub+strength) | ⏳ Deferred |

**Experiment log:** [`EXPERIMENT_LOG.md`](../EXPERIMENT_LOG.md) at repo root, auto-generated from the `meta.json` + `aligned.json` files for every run. 60 (doc, version) tuples right now. Regenerate with `python3 -m src.build_experiment_log`.

**Evaluation numbers on Alphabet 2024 (38 human anchors):**

| Version | Method | AI tags | Anchors caught | Missed |
|---|---|---:|---:|---:|
| V0 baseline | full doc, one call | 52 | 12 | 30 |
| V1 keyword_window_20 | keyword + ±20 sentences | 54 | 13 | 29 |
| V2 keyword_per_sentence | keyword + matched sentence alone | 166 | 26 | 16 |
| V3 sequential_batched | 4-phase chain | 55 | 20 | 22 |
| V4 hai_tuned_oneshot | one-shot + HAI v1 rules | 43 | 14 | 28 |
| V4.1 hai_tuned_oneshot_v2 | one-shot + HAI v2 principles | 42 | 14 | 28 |
| V5 sequential_passage_aware | 6-phase + HAI v3 guardrails | 51 | 20 | 22 |
| **V6** xml_cot_baseline | V0 shape + XML `<Reasoning>` per tag | 73 | **22** | 20 |
| **V7** n_sentence_chunk_20 | 20-sentence non-overlapping chunks | 253 | **26** | 16 |
| **V8** n_sentence_chunk_40 | 40-sentence non-overlapping chunks | 175 | 21 | 21 |

V3 and V5 tie at 20 — but a different 20 each; combined coverage would be 24. V6 is the strongest single-call result at 22. V7 ties V2 for the highest catch count (26) but tags 5× as much as V0 — over-tagging is the tradeoff.

**Direct question back on your redundancy note:** we currently only dedupe exact `(sentence, kind, category, subcategory)` tuples per doc. Two different sentences making the same point in different words both count. How do you want redundancy handled in the scoring? Options I've been thinking about:
1. Semantic dedup via embeddings (report "distinct claims" alongside "total tags")
2. Per-category weighted recall (1/N credit for a claim covered N times)
3. Just document the number and don't try to normalize

Would love your take before I commit to one.

Let me know if you'd like me to walk through any of this live. The Netlify site (link in the README) is the fastest way to see the strategies side-by-side.

Best,
Pranav
