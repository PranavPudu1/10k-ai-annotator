# Draft update message

Copy-paste this into Slack/email. Fill in the recipient's name and adjust tone as needed.

---

Hi [Name],

Great timing — I have a good update. I've been running the automated tagging experiments for a while and just packaged everything up in a dedicated repo. Answering your priorities in order:

**Code:** https://github.com/PranavPudu1/10k-ai-annotator (private — happy to add you as a collaborator; send me your GitHub handle). The README has a quickstart and a link to a live Netlify site where you can browse all of the experiments without cloning anything.

**Is this Naomi's pipeline?** No, but it shares foundations — same AI-keywords list, same taxonomy, same keyword-window chunking concept. Full comparison at `docs/vs_naomi.md`. TL;DR: (1) the LLM annotator (`src/`) ingests EDGAR HTML directly (not Naomi's SGML) and runs 7 versioned strategies; (2) our separate human annotation Flask app (`annotation_tool/`, not shared in this repo — that's the annotator UI we built to replace Prodigy) eats her `sections.jsonl` output verbatim. Sentence splitter is upgraded from her regex to `pysbd` in both — deliberate call documented in `annotation_tool/SEGMENTER_DECISION.md`.

**Sentence-splitting fragments — was this fixed?** Diagnosed all 16 HAI-flagged fragment cases. Only 3 are still present in the current pipeline; the rest are either stale anchor references from an earlier index or list-format artifacts (bullets, colon-headers). Not an abbreviation-splitting bug like we initially assumed. `pysbd` handles decimals, abbreviations, `Ph.D.`, `EU AI Act`, etc. correctly. **Skipping the splitter fix for now** — full write-up in `docs/diagnostics_2026-07-14.md`.

**Chain-of-thought / reasoning traces:** V5 (our best-performing sequential strategy) already emits a per-verdict `reason` field on Phase 3 (context filter), averaging 151 characters and citing the passage context. It's chain-of-thought — just not wrapped in `<Reasoning>` XML. Surfaced verbatim on the Missed Human Tags tab of the V5 page on Netlify (highlighted in blue). Adding schema-wide `<Reasoning>` to V0/V1/V2/V4/V4.1 is deferred until we're iterating on one of those.

**Prompt iteration on the two error modes (over-tagging non-RAI + missing context):**
- **Over-tagging non-RAI:** did a full deep read of 844 HAI reviewer verdicts (Naomi + Angie) and distilled 15 principles. That's V4.1 (`data/hai_dont_rules_v2.md`). Reduces tags from 52 → 42 on Alphabet 2024.
- **Missing context:** V5 targets this directly. Phase 1 identifies AI-topic passages at section level; sentences inside those passages get considered even when they don't themselves say "AI". Recovers 4 Legal/context anchors V3 misses.

**Units + Pipeline (your options A/B/C/D + all-at-once/sequential):**

| Units | Status |
|---|---|
| A. Whole doc | ✅ V0 baseline |
| B. Fixed N-sentence chunks | ⏳ Not done — deferred |
| C. Keyword ± N window | ✅ V1 (window merging) + V2 (per-sentence isolation) |
| D. BM25 | ⏳ Deferred |

| Pipeline | Status |
|---|---|
| All at once | ✅ V0, V4, V4.1 |
| Sequential (kind → cat/sub → strength) | ✅ V3 (4 phases) |
| Sequential + passage-level context step | ✅ V5 (6 phases) |
| Hybrid (kind → cat/sub+strength) | ⏳ Deferred |

**Experiment log:** `EXPERIMENT_LOG.md` at repo root, auto-generated from the `meta.json` + `aligned.json` files for every run. 57 (doc, version) tuples right now. Regenerate with `python3 -m src.build_experiment_log`.

**Evaluation numbers on Alphabet 2024 (38 human anchors + 4 unmatched-alignment):**

| Version | Method | AI tags | Anchors caught | Missed |
|---|---|---:|---:|---:|
| V0 baseline | full doc, one call | 52 | 12 | 30 |
| V1 keyword_window_20 | keyword + ±20 sentences | 54 | 13 | 29 |
| V2 keyword_per_sentence | keyword + matched sentence alone | 166 | 26 | 16 |
| V3 sequential_batched | 4-phase chain | 55 | 20 | 22 |
| V4 hai_tuned_oneshot | one-shot + HAI v1 rules | 43 | 14 | 28 |
| V4.1 hai_tuned_oneshot_v2 | one-shot + HAI v2 principles | 42 | 14 | 28 |
| **V5** sequential_passage_aware | 6-phase + HAI v3 guardrails | 51 | **20** | 22 |

V3 and V5 tie at 20 — but a different 20 each; combined coverage would be 24. V5 catches Legal-context misses V3 lacks; V3 catches EU AI Act sentences V5 drops (V5's Phase 3 filter is too aggressive on those — targeted fix is a prompt tweak).

**Direct question back on your redundancy note:** we currently only dedupe exact `(sentence, kind, category, subcategory)` tuples per doc. Two different sentences making the same point in different words both count. How do you want redundancy handled in the scoring? Options I've been thinking about:
1. Semantic dedup via embeddings (report "distinct claims" alongside "total tags")
2. Per-category weighted recall (1/N credit for a claim covered N times)
3. Just document the number and don't try to normalize

Would love your take before I commit to one.

Let me know if you'd like me to walk through any of this live. The Netlify site (link in the README) is the fastest way to see the strategies side-by-side.

Best,
Pranav
