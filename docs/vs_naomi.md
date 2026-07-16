# Relationship to Naomi's original pipeline

Two of our components touch Naomi's work. They relate to it differently.

## `src/` — the LLM annotator

**Shares foundations with Naomi, extends downstream.**

| Aspect | Naomi's pipeline (`Responsible-AI-Based-Investment-main/`) | Ours (`src/`) |
|---|---|---|
| AI keywords | 195 terms in `filter-and-upload-to-hf/ai-keywords.txt` | **Same list** — literally copied into `data/ai_keywords.txt` |
| Taxonomy | RAI Finance Pilot Information CSVs | **Same** CSVs, unchanged |
| Chunking concept | ±N sentence window around keyword hits | **Same concept** — implemented as our V1 `keyword_window_20` in [src/chunkers.py](../src/chunkers.py) `keyword_window_chunker` |
| Input format | SEC EDGAR **full-submission SGML** | EDGAR **HTML** via [data/fetch_10ks.py](../data/fetch_10ks.py) + BeautifulSoup extraction |
| Sentence splitter | `re.compile(r'(?<=[.!?])\s+')` (plain regex) — breaks on `$7.4 billion`, `12.3%`, `U.S.`, `Ph.D.`, `Section 7.4.4` | `pysbd` — handles decimals, abbreviations, section numbers. Documented decision in [annotation_tool/SEGMENTER_DECISION.md](../annotation_tool/SEGMENTER_DECISION.md) |
| Section extraction | Splits at Item boundaries (Item 1, 1A, 1C, 7) | None — processes full doc; V5 identifies AI-topic passages at annotation time via LLM |
| Downstream purpose | Emit `sections.jsonl` with sentence spans + keyword char-offsets → upload to Hugging Face | LLM annotation → per-strategy `ai_annotations.json` + aligned metrics vs human ground truth + versioned experiments UI |

**One-line summary:** Naomi's pipeline stops at "here are the keyword-relevant sentence spans." Ours starts around there and adds LLM annotation, 10 versioned strategies, and evaluation against human ground truth.

## `annotation_tool/` — the human annotation Flask app

**Consumes Naomi's output format directly, with a fixed segmenter.**

- [annotation_tool/ingest.py](../annotation_tool/ingest.py) opens with `"""Walk Naomi's output directory, ingest into the annotation_tool DB."""` — it reads her `sections.jsonl` files verbatim, per `{cik}/{section_type}/{accession}/` directory.
- Segmentation at ingest uses `pysbd` via [annotation_tool/segmenter.py](../annotation_tool/segmenter.py), *not* her regex. This was a deliberate correction documented in [annotation_tool/SEGMENTER_DECISION.md](../annotation_tool/SEGMENTER_DECISION.md), which compares pysbd vs NLTK on 10-K prose with real edge cases (decimals, abbreviations, section numbers, honorifics).
- Web UI, name-picker auth, DB-backed storage, per-user views, and inter-annotator adjudication are all ours. Naomi's team used **Prodigy**; we built a Flask replacement.
- The RAI taxonomy and the annotation model (highlight sentence → assign kind + category + subcategory + strength) come straight from Naomi's project.

**One-line summary:** `annotation_tool/` eats Naomi's `sections.jsonl` format and uses her taxonomy exactly. We swapped her regex splitter for pysbd (documented) and built a custom Flask UI instead of using Prodigy. Same annotation model, different tool.

## Combined answer

*"No, this isn't Naomi's exact pipeline — but it shares foundations. Same AI-keywords list, same taxonomy, same keyword-window chunking concept. On top of that we've built (1) a versioned LLM annotator (`src/`) that ingests EDGAR HTML directly and runs 7 different strategies, and (2) a human annotation Flask app (`annotation_tool/`) that eats her `sections.jsonl` output and replaces Prodigy. The sentence splitter is upgraded from her regex to pysbd in both places — a deliberate decision documented in [annotation_tool/SEGMENTER_DECISION.md](../annotation_tool/SEGMENTER_DECISION.md)."*
