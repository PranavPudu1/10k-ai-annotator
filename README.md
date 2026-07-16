# 10-K RAI Annotator

An automatic tagger that reads a 10-K filing and labels sentences with AI-related risks and risk-mitigations, so we can compare what the AI catches vs. what human researchers catch on the same document.

- **Live site to browse results:** https://warm-sawine-c7631b.netlify.app
- **The reference doc I'm responding to below:** "Notes on LLM prompting experiments" [Google Doc](https://docs.google.com/document/d/1Z3y9SuAL3ujBw8sOOr5wR8YaloadKsdivELBpYrBiBg).

Each section below quotes the notes doc verbatim, then answers in three short parts:

- **What we did.** What's already built.
- **What we could try next.** Concrete next step, if there is one.
- **What we'd need to discuss.** An open question that needs a decision.

If a part isn't relevant, it's skipped. If we haven't done something, it just says *To do.*

---

## Done so far

> Done so far: Prompt with entire 10k as context. Prompt iteration.

**What we did.** We're on version 8 now. All ten versions (V0–V8) are on the live site. Numbers on Alphabet 2024 (38 human-tagged sentences):

| Version | Method | AI tags | Sentences caught | Sentences missed |
|---|---|---:|---:|---:|
| V0 baseline | Feed the whole 10-K in one shot | 52 | 12 | 30 |
| V1 keyword_window_20 | Only feed sentences near AI-keyword hits (±20 sentence window) | 54 | 13 | 29 |
| V2 keyword_per_sentence | Feed each keyword-matching sentence alone, no context | 166 | 26 | 16 |
| V3 sequential_batched | Chain of 4 short LLM calls, one per decision | 55 | 20 | 22 |
| V4 hai_tuned_oneshot | V0 but with prompt rules from Naomi + Angie's feedback (v1 rules) | 43 | 14 | 28 |
| V4.1 hai_tuned_oneshot_v2 | V4 with deeper rules (v2, 15 principles from all 844 feedback rows) | 42 | 14 | 28 |
| V5 sequential_passage_aware | Chain of 6 short calls, with a step that finds AI-topic passages first (v3 rules) | 51 | 20 | 22 |
| **V6** xml_cot_baseline | Same as V0 but each annotation carries an XML `<Reasoning>` chain-of-thought | 73 | **22** | 20 |
| **V7** n_sentence_chunk_20 | Split doc into non-overlapping 20-sentence chunks, tag each | 253 | **26** | 16 |
| **V8** n_sentence_chunk_40 | Same as V7 but 40-sentence chunks | 175 | 21 | 21 |

V7 ties V2 for the highest catch count (26/38) but tags 5× as much as V0 — over-tagging is the tradeoff. V6 is the best single-call result at 22/38 with modest over-tagging. V3 and V5 remain the balanced precision-aware picks. V4/V4.1 stay the most conservative.

*See [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md) for the full log across every run.*

---

## Need — an experimental log

> Need: Experimental log/journal of things tried, and summary statistics (also include reports/data that you processed).

**What we did.** [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md) is auto-generated from every version's saved config and result files. Regenerate with `python3 -m src.build_experiment_log`. The reports and data I processed to derive the prompt rules are in [`hai-annotations/`](hai-annotations/), and my analysis of them is in [`docs/diagnostics_2026-07-14.md`](docs/diagnostics_2026-07-14.md).

**What we could try next.** Mirror the log to a Google Sheet or Notion if that's a better surface for you — the markdown source copy-pastes cleanly.

---

## Problem setup

> Problem setup: Input: sentences. Output: label for each sentence where label is (risk/mitigation, subcategory, strength).

**What we did.** Exactly this. Sentences come from a splitter (`pysbd`) run on the 10-K text. Labels are pulled from the RAI taxonomy CSVs. Each label is `(kind, category, subcategory, strength)`. Data lives under [`data/`](data/) and [`output/`](output/).

**On sentence splitting (from the follow-up: "was this fixed?"):** yes, it's fixed. We diagnosed all 16 fragment cases flagged by the HAI reviewers — 3 were real fragments still present in the current output (list headers ending in `:` and lowercase continuations after bullets in `amazon_2024`, `meta_2024`, `oracle_2024`). The other 13 pointed at anchor IDs from an earlier indexing that no longer exist. We added a post-splitter merge pass in [`src/sentence_index.py`](src/sentence_index.py) with two rules (merge on colon-ended sentence; merge on lowercase continuation) and re-indexed the 3 affected docs. Verified with unit tests, regression against clean 10-K prose (decimals, `Ph.D.`, `EU AI Act`, section numbers all still split correctly), and sanity-check on 5 random docs (2.7–3.8% sentence-count drop, no colon-ends or lowercase-starts in the first 100 sentences). Full diagnostic in [`docs/diagnostics_2026-07-14.md`](docs/diagnostics_2026-07-14.md).

---

## Goals

> Goals: Automatic tagging should be accurate: minimize false positives and false negatives. We also want to keep the cost and time reasonable. (Optional, but useful) human-understandable explanations for why things got tagged a certain way.

**What we did.**
- **Accuracy:** best current human overlap is 20 of 38 human anchors (V3 and V5). V4.1 makes the fewest false positives.
- **Cost + time:** V5 costs ~$0.05 per doc, runs in ~30 seconds. Everything except V2 is cheap.
- **Explanations:** V5 already writes a plain-English reason for every keep/drop decision in its filtering step. Sample: *"Inside a sustainability passage, this explicitly identifies uncertainty around AI's future environmental impact as a risk consequence."*

**What we'd need to discuss.** No version catches more than 20 of 38 sentences without also 3×-over-tagging (V2). The remaining gap is mostly Legal-context sentences where the sentence itself doesn't say "AI" — humans read the surrounding paragraph and tag anyway. Willing to try V5.1 with a looser filtering step if that seems worth it.

---

## Question — redundancy

> Questions (unresolved): is it a problem that there is likely redundancy in sentences (many tagged sentences on the same point or topic will inflate the score).

**What we did.** Right now the code only removes exact repeats (same sentence, same tag). Two different sentences saying the same thing both count.

**What we'd need to discuss.** Three ways I could handle this — none built yet, and I'd like to pick one before implementing:

1. Cluster tagged sentences per category by meaning (using embeddings) and report a "distinct claims" count next to the "total tags" count.
2. Weighted recall — if humans tag 4 sentences on the same claim, give 1/4 credit each.
3. Merge consecutive sentences that got the same tag.

Which direction fits how you want the score to read?

---

## Prompt instruction

> Prompt instruction: Instructions can start with what the human annotators get. Iterate on the instruction based on the errors seen. Sometimes instructions are hard for LLMs to follow. Examples can help (but try to balance them between the different categories).

**What we did.** I've iterated on the instructions three times using Naomi and Angie's actual feedback on the baseline output (876 verdicts in [`hai-annotations/`](hai-annotations/)):

- v1 rules → V4. 12 rules I hand-distilled from the short labels.
- v2 rules → V4.1. 15 principles from reading every long-form explanation.
- v3 rules → V5. v2 but with the strict "AI must be in the adjacent paragraph" rule dropped, plus new passage-aware guidance.

Few-shot examples are balanced across categories in the picker code.

**On the follow-up question — "do the errors go away when specified explicitly?"** Empirical answer: measurably yes, not fully.

*Error 1 — "tagging for AI even if it's not specific to RAI"* (over-tagging on non-AI content). AI tag count drops as rules get more specific:

| Version | AI tags | Sentences caught |
|---|---:|---:|
| V0 no rules | 52 | 12 |
| V4 v1 rules | 43 | 14 |
| V4.1 v2 rules | 42 | 14 |
| V5 v3 rules + passage-aware | 51 | 20 |

Rules cut over-tagging by ~19% (52 → 42) while lifting recall. V5 tags more than V4.1 because its passage step surfaces genuine AI-topic sentences, not because the rules got looser.

*Error 2 — "failing to tag things due to missing context"* (under-recall on context-driven sentences). Anchors caught climbs:

| Version | Anchors caught |
|---|---:|
| V0 baseline | 12 |
| V4.1 rules alone | 14 |
| V3 sequential (no passage step) | 20 |
| V5 passage-aware sequential | 20 |

Sequential staging (V3) helps by 8. Adding passage discovery (V5) matches V3 but catches a different set — V5 recovers 4 Legal/context sentences V3 misses; V3 catches 4 EU-AI-Act sentences V5's filter drops. Combined coverage would be 24 of 38.

**Honest bottom line.** Rules measurably reduce both error modes. Neither is fully solved. Legal/Uncertainty-in-AI-regulation-passages remains the dominant residual miss category — see [`docs/diagnostics_2026-07-14.md`](docs/diagnostics_2026-07-14.md).

**What we could try next.** Keep iterating on v3 based on new errors. A v4 rule set targeting Legal-context specifically is the obvious next iteration.

---

## Units — chunk input sizes

### A. Entire document

> A) Entire document (done, I think this will be a weak baseline).

**What we did.** V0. Yes, weak baseline — 12 of 38 sentences caught, over-tagging is the failure mode.

### B. Split doc into chunks (N sentence)

> B) Split doc into chunks (e.g., N sentence chunks, maybe try 20, 40) – ask it to tag everything inside.

**What we did.** Built two versions:

- **V7 — 20-sentence chunks.** Slide a 20-sentence non-overlapping window across the whole doc, tag everything inside each chunk. 105 chunks on Alphabet 2024, 253 tags, 26 caught.
- **V8 — 40-sentence chunks.** Same but 40-sentence windows. 53 chunks, 175 tags, 21 caught.

**What we learned.** Smaller chunks catch more human anchors (V7 = 26 vs V0 = 12) but the tradeoff is heavy over-tagging: V7 emits 253 tags vs V0's 52. V8 (larger chunks) sits in the middle — 21 caught, 175 tags. The 20-sentence variant looks like a strong retrieval signal but needs a second-pass filter to be usable as final output.

### C. Keyword ±20 sentence context

> C) For each sentence containing an AI keyword(s), take the 20 sentences before and after (mirroring what our annotators are doing), and ask the LM to annotate only that sentence (in context). (Disadvantage: we can't find if annotators missed anything outside of this set; also higher cost and time).

**What we did.** Two versions:

- V1 — keyword hits with ±20 sentence window, overlapping windows merged.
- V2 — same keyword filter, but only the matched sentence is fed to the LLM (no neighbors). Over-tags hard, as expected.

**What we'd need to discuss.** On Alphabet 2024 the ±20 windows merge into ~99% of the doc anyway (Alphabet is very AI-dense), so V1 is basically identical to V0 baseline. A better test on a low-AI-density doc (Tesla, Netflix) would actually differentiate them. Want me to run one?

### D. BM25

> D) (LATER) If we need to go beyond this keyword approach, we could try BM25.

*To do — you marked it LATER, we're keeping it LATER.*

---

## Pipeline — for each input unit

> Pipeline: for each input unit — Prompt for all outputs all at once (task vs mitigation, subcategory, strength) — Prompt sequentially: 1) Prompt for task vs mitigation → 2) depending on answer prompt for subcategory (prompt is different for risk & mitigation) → 3) prompt for strength — Perhaps if strength is something that should be decided at the same time as the subcategory, we could try: 1) task vs mitigation → 2) subcategory+strength.

**What we did.**
- **All at once:** V0, V4, V4.1.
- **Sequential (kind → cat/sub → strength):** V3. Matches your 3-step chain exactly.
- **Sequential + passage step:** V5. Adds a first step that finds AI-topic passages, so downstream steps see section-level context.

**What we could try next.** The hybrid you mentioned — subcategory + strength together in one call. Not built yet. *To do.*

> Note: an advantage of pipeline approach is it can be easier for LLMs to follow more specific instructions, one at a time, rather than multiple instructions at once.

Confirmed empirically. V3 (sequential) catches 20 sentences vs. V0's 12 on the same doc.

---

## Structure — thinking tokens

> Structure: Should try asking for thinking tokens, i.e., in `<REASONING> … </REASONING>`, followed by `<ANSWER> </ANSWER>` (Goal: better accuracy, and tool for debugging). If using a Reasoning LM, can also report the thinking trace (or summary, depends on the model).

**What we did.** Built a new version — **V6 — Baseline + XML `<Reasoning>` CoT** — that implements this format literally. Every annotation V6 emits carries a `reasoning` field whose content is wrapped in `<Reasoning>...</Reasoning>` tags. 73 out of 73 annotations on Alphabet 2024 have one. Real V6 sample:

- Sentence: *"We believe our approach to AI must be both bold and responsible."*
- Reasoning: `<Reasoning>The phrase "must be both bold and responsible" is a general commitment to manage AI responsibly. This is an intention-level mitigation without specific controls, so strength 1 fits.</Reasoning>`

**How existing versions overlap:**

- **V5 (sequential_passage_aware)** already emits reasoning too, just not in XML. Its Phase 3 (context filter) has a required `reason` field on every keep/drop verdict. 205/205 verdicts on Alphabet 2024, averaging 151 characters, citing passage context. Same debugging value as V6's XML reasoning — different wrapping. Rendered in blue on the V5 "Missed Human Tags" tab.
- **V0, V1, V2, V3, V4, V4.1** don't emit reasoning. Their outputs are annotations only. If we want CoT on those, the fix is straightforward — add a `reasoning` field to their schemas and re-run. Deferred because V6 already answers the question and the other versions aren't the ones we're actively iterating on.

**What we'd need to discuss.** We're using gpt-5.4-mini, not a reasoning model. If we switch to o1 or Claude with `thinking` enabled, the model's own thinking trace lands in the raw response cache alongside the JSON output — no schema change needed.

*Comparing V6's tag counts to V0 baseline is interesting on its own: V6 = 73 tags, 22 caught, vs V0 = 52 tags, 12 caught. Asking the model to justify each tag surfaces genuine annotations V0 skipped.*

---

## Outputs

> Outputs: Save — All LLM outputs in a log (for debugging or analysis purposes later) — The predicted output tags (sentence id → tag).

**What we did.** Both saved per (doc, version) under `output/{slug}/versions/{version_id}/`:

- Raw LLM output cache — `llm_raw_response.json`. For the sequential versions (V3, V5) it's split by phase so we can rerun individual phases without paying for the whole chain again.
- Predicted tags — `ai_annotations.json` (validated + deduped) and `aligned.json` (matched against human tags with counts).
- Strategy config + timestamp — `meta.json`, so the experiment log can auto-generate.

---

## Evaluation

> Evaluation – Summary statistics/metrics: Precision and Recall — Risk vs Mitigation: precision, recall, F1 — All subcategories (for now, separately per subcategory), as well as macro-{precision, recall, F1} — Strength statistics — Confusion matrices (risk vs mitigation, subcategories, strength) — Sample examples (examples of errors for each category; false positives and false negatives). Thinking traces/CoT will also help debugging and iterating the prompt or prompting approach.

**What we did.** All on the live site under the "Evaluation" and "Missed Human Tags" tabs per version:

- Per-subcategory precision, recall, F1.
- Macro / micro / weighted rollups.
- Category confusion matrix.
- Sample false positives and false negatives — "Missed Human Tags" lists every human-tagged sentence the AI missed, with the human's tag, the sentence, and (for V3 and V5) which step in the chain lost it.
- V5's reasoning trace shown inline on that page.

**What we could try next.**
- Risk vs Mitigation precision/recall as its own dedicated view (currently it's inside the per-subcategory numbers). *To do.*
- Strength confusion matrix as its own view. *To do.*

---

## Please make a new tab (or use Google Sheets, or Notion...)

> Please make a new tab (or use Google Sheets, or Notion, or some other way if you have a workflow you like) to track experiments and results — so we have a record to track what was tried and how it went.

**What we did.** The auto-generated log at [`EXPERIMENT_LOG.md`](EXPERIMENT_LOG.md). Regenerates any time we run new experiments.

**What we could try next.** Mirror the markdown to a Google Sheet or Notion table if either is a better surface for you. Just let me know which.

---

## CLI flags for units and pipelines

> Ideally changing units and pipeline approaches etc can be done with command line flags so it's easy to run and track.

**What we did.** Right now the CLI takes a single `--version` flag with a preset name that bundles chunker + pipeline + rules together. Example:

```
python3 -m src.pipeline --doc alphabet_2024 --version sequential_passage_aware
```

The 7 presets cover the combinations we've tried. It works, but it's not what you're asking for — you can't mix chunker A with pipeline B and rules C without adding a new preset in code.

**What we could try next.** Refactor the CLI to take three independent flags:

```
python3 -m src.pipeline --doc alphabet_2024 --chunker keyword_window --pipeline sequential --rules v3
```

Then you can sweep experiments from the command line. This is bounded work — 2–3 hours. *To do.*

---

## Comparison with Naomi's pipeline

> Also, could you share the code you are using? I wasn't sure if you were using the same pipeline as Naomi or not.

**What we did.** The code is this repo. It's not exactly Naomi's pipeline — same keyword list, same taxonomy, same "keyword ± N sentence" concept (that's V1), but we ingest EDGAR HTML directly (not her SGML) and use `pysbd` for splitting instead of her regex.

*Full side-by-side in [`docs/vs_naomi.md`](docs/vs_naomi.md).*

---

## Try it yourself

Clone the repo, add your OpenAI API key, run V5 on Alphabet 2024:

```bash
git clone https://github.com/PranavPudu1/10k-ai-annotator
cd 10k-ai-annotator
pip install -r requirements.txt

cp .env.local.example .env.local
# then edit .env.local and paste your OpenAI key

python3 -m src.pipeline --doc alphabet_2024 --version sequential_passage_aware
streamlit run src/app.py
```

Cost: about $0.05. Time: about 30 seconds. If you'd rather skip the run and just look at what's already there, all seven versions' outputs are checked in under [`output/alphabet_2024/versions/`](output/alphabet_2024/versions/).

To run a different version, swap `sequential_passage_aware` for any of: `baseline`, `keyword_window_20`, `keyword_per_sentence`, `sequential_batched`, `hai_tuned_oneshot`, `hai_tuned_oneshot_v2`.

---

## Repo layout

```
10k-ai-annotator/
├── src/                       LLM annotator code
├── data/                      taxonomy CSVs, keyword list, prompt rules, human tags
├── output/{slug}/versions/{version_id}/    per-run saved outputs
├── hai-annotations/           Naomi + Angie's feedback CSVs (used to derive the prompt rules)
├── docs/
│   ├── notes_doc_mapping.md   the same walk-through but as a status table
│   ├── vs_naomi.md            side-by-side with Naomi's pipeline
│   └── diagnostics_2026-07-14.md   deeper notes on 4 specific asks
├── EXPERIMENT_LOG.md          auto-generated
└── README.md                  this file
```
