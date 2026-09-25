# Data dictionary: adjudicated 10-K annotations

Updated 2026-09-25. Sample filing: Workday 2025 (Amali Oakley and Joseline Viveros), fully adjudicated.

## The files

| File | What it is | One row per |
|---|---|---|
| `final_labels.csv` | The label that stands for each tagged sentence after adjudication, with where it came from. Use this for analysis. | tagged sentence |
| `annotations.csv` | Every tag by every annotator, with the final decision on each row. The dataset. | tag |
| adjudication report | Only the sentences the two annotators disagreed on, with both sides and the final decision. | disputed sentence |
| `filings.csv` | Per-filing summary: annotators, counts, whether adjudication is done. Includes filings with no AI content. | filing |

Where: `tool-exports/` in this repo has the whole corpus (`final_labels.csv`, `annotations.csv`, `filings.csv`, and one file per company-year under `by-company/`), refreshed daily. The Manage page of the tool has the same downloads per filing, plus the adjudication report.

## How to read the files

- `final_labels.csv`: one row per sentence. `final_tags` is the label; `final_source` says whether it was agreed, decided in adjudication, or is still pending.
- One row is one tag by one annotator. A sentence tagged by both people appears once per person.
- A tag covering several sentences is one row. `sentence_ordinal` lists the sentences.
- Which label to use: `final_tags` if `adjudicated_status` is resolved, the tag itself if agreed, none yet if disputed.
- `resolved_to_none` = true means the decision was "no tag".
- `filing_finalized` = true means adjudication of the whole filing is done.
- Only the six annotators on real filings are in the corpus file. No screening, admin or demo data.

## final_labels.csv

| # | Column | Meaning |
|---|---|---|
| 1 | `doc_id` | Filing id in the tool. |
| 2 | `cik` | The company's SEC id, 10 digits. |
| 3 | `company` | Company name. |
| 4 | `year` | Filing year. |
| 5 | `accession` | SEC accession number of the 10-K. |
| 6 | `section_name` | The 10-K section the sentence is in. |
| 7 | `sentence_ordinal` | Sentence number within the filing. One sentence per row, always. |
| 8 | `sentence_text` | The sentence. |
| 9 | `final_tags` | The label(s) that stand for this sentence, separated by '; '. Blank if resolved to no tag or still pending. |
| 10 | `final_source` | Where the label came from: agreed (both gave it), resolved (decided in adjudication), resolved_to_none (decided: no tag), resolved_span (decided on another sentence of the same span), solo (only one annotator on the filing), pending (still disputed). |
| 11 | `n_final_tags` | How many final tags the sentence has. |
| 12 | `annotator_a` | First annotator (alphabetical). |
| 13 | `annotator_a_tags` | Their original tags on this sentence. |
| 14 | `annotator_b` | Second annotator. Blank on single-annotator filings. |
| 15 | `annotator_b_tags` | Their original tags on this sentence. |
| 16 | `strength_disputed` | true if both gave the same Mitigation tag but different strengths. |
| 17 | `span_ordinals` | If the sentence is part of a multi-sentence tag, the span's first and last sentence numbers. |
| 18 | `resolved_by` | Who recorded the decision. |
| 19 | `resolved_at` | When the decision was recorded (UTC). |
| 20 | `n_comments` | Adjudication comments on this sentence. |
| 21 | `filing_finalized` | true if adjudication of the whole filing was marked done. |
| 22 | `adjudication_done_at` | When adjudication was marked done (UTC). |
| 23 | `archived` | true if the filing has been archived. |

## annotations.csv

| # | Column | Meaning |
|---|---|---|
| 1 | `cik` | The company's SEC id, 10 digits. |
| 2 | `company` | Company name. |
| 3 | `year` | Filing year. |
| 4 | `accession` | SEC accession number of the 10-K. |
| 5 | `section_name` | The 10-K section the sentence is in. 'Full Document' if no section headings were found. |
| 6 | `sentence_ordinal` | Sentence number within the filing. A comma-separated list if the tag covers several sentences. |
| 7 | `sentence_text` | The sentence. Joined text if the tag covers several sentences. |
| 8 | `has_ai_keyword` | true if the sentence contains an AI keyword. |
| 9 | `matched_keywords` | The AI keywords found, separated by '; '. |
| 10 | `annotator_name` | Who made the tag. |
| 11 | `kind` | Risk, Mitigation, or Responsible AI Commitment Statement. |
| 12 | `category` | Taxonomy category. '-' for Commitment tags. |
| 13 | `subcategory` | Taxonomy subcategory. '-' for Commitment tags and for AI Safety (General, Broad). |
| 14 | `strength` | 1 to 3 for Mitigation tags (see the strength rubric). Blank for other kinds. |
| 15 | `note` | The annotator's note on the tag, if any. |
| 16 | `status` | The annotator's status on this filing: done or in_progress. Frozen at archive time for archived filings. |
| 17 | `disputed` | true if the two annotators disagreed on this sentence: one did not tag it, or their tags differ. Strength and notes do not count. Same value on every row of the sentence. |
| 18 | `pair_disputed` | true if the other annotator did not give this same tag on this sentence. |
| 19 | `group_id` | Id of a multi-sentence tag. Blank for single-sentence tags. |
| 20 | `spans_n_sentences` | How many sentences the tag covers. |
| 21 | `context_sentence_ordinals` | Sentence numbers the annotator attached as extra context. |
| 22 | `context_sentence_text` | Text of those context sentences. |
| 23 | `adjudicated_status` | agreed (both gave the same tag), disputed (waiting on adjudication) or resolved (final decision recorded). In the adjudication report: resolved or unresolved. Blank only on the two Baxter filings adjudicated in Google Sheets. |
| 24 | `final_kind` | Kind of the first final tag. Blank unless resolved. |
| 25 | `final_category` | Category of the first final tag. Blank unless resolved. |
| 26 | `final_subcategory` | Subcategory of the first final tag. Blank unless resolved. |
| 27 | `final_strength` | Strength of the first final tag (Mitigation only). Blank unless resolved. |
| 28 | `final_tags` | All final tags for the sentence, separated by '; '. Use this one. Blank on a resolved row means 'no tag'. |
| 29 | `doc_id` | Filing id in the tool. Joins to filings.csv. |
| 30 | `annotation_id` | Id of this tag. Unique per row. |
| 31 | `annotator_id` | Id of the annotator's account. |
| 32 | `resolved_to_none` | true if adjudication decided the sentence gets no tag. |
| 33 | `resolved_by` | Who recorded the final decision. |
| 34 | `resolved_at` | When the final decision was recorded (UTC). |
| 35 | `n_comments` | Number of adjudication comments on the sentence. |
| 36 | `adjudication_comments` | The comments, as 'Name (time): text', separated by ' \| '. |
| 37 | `strength_disputed` | true if both gave the same Mitigation tag but different strengths. |
| 38 | `filing_finalized` | true if adjudication of the whole filing was marked done. |
| 39 | `adjudication_done_at` | When the filing's adjudication was marked done (UTC). |
| 40 | `archived` | true if the filing has been archived. |

## Adjudication report

| # | Column | Meaning |
|---|---|---|
| 1 | `cik` | The company's SEC id, 10 digits. |
| 2 | `company` | Company name. |
| 3 | `year` | Filing year. |
| 4 | `accession` | SEC accession number of the 10-K. |
| 5 | `section_name` | The 10-K section the sentence is in. 'Full Document' if no section headings were found. |
| 6 | `sentence_ordinal` | Sentence number within the filing. A comma-separated list if the tag covers several sentences. |
| 7 | `sentence_text` | The sentence. Joined text if the tag covers several sentences. |
| 8 | `annotator_a` | First annotator (alphabetical). |
| 9 | `annotator_a_tags` | Their tags on the sentence, separated by '; '. |
| 10 | `annotator_b` | Second annotator. |
| 11 | `annotator_b_tags` | Their tags on the sentence, separated by '; '. |
| 12 | `adjudicated_status` | agreed (both gave the same tag), disputed (waiting on adjudication) or resolved (final decision recorded). In the adjudication report: resolved or unresolved. Blank only on the two Baxter filings adjudicated in Google Sheets. |
| 13 | `final_tags` | All final tags for the sentence, separated by '; '. Use this one. Blank on a resolved row means 'no tag'. |
| 14 | `resolved_by` | Who recorded the final decision. |
| 15 | `resolved_at` | When the final decision was recorded (UTC). |
| 16 | `n_comments` | Number of adjudication comments on the sentence. |
| 17 | `adjudication_comments` | The comments, as 'Name (time): text', separated by ' \| '. |

## filings.csv

| # | Column | Meaning |
|---|---|---|
| 1 | `doc_id` | Filing id in the tool. Blank for filings with no AI content. |
| 2 | `cik` | The company's SEC id, 10 digits. |
| 3 | `company` | Company name. |
| 4 | `year` | Filing year. |
| 5 | `accession` | SEC accession number of the 10-K. |
| 6 | `no_ai_content` | true if the filing had no AI-related sentences, so there was nothing to annotate. |
| 7 | `is_screening` | true for screening filings. Only included on request. |
| 8 | `archived` | true if the filing has been archived. |
| 9 | `n_sentences` | Number of sentences in the filing. Blank for older archived filings. |
| 10 | `n_keyword_sentences` | Number of sentences with an AI keyword. |
| 11 | `annotators` | The filing's annotators, separated by '; '. |
| 12 | `annotator_statuses` | Each annotator's status, as 'Name=status'. |
| 13 | `annotator_done_at` | When each annotator marked the filing done, as 'Name=time' (UTC). |
| 14 | `n_expected_annotators` | How many annotators were assigned. |
| 15 | `filing_finalized` | true if adjudication of the filing was marked done. |
| 16 | `adjudication_done_at` | When adjudication was marked done (UTC). |
| 17 | `legacy_sheet_url` | Google Sheet link for filings adjudicated outside the tool. |
| 18 | `n_tagged_sentences` | Sentences with at least one tag. |
| 19 | `n_agreed` | Tagged sentences both annotators agreed on. |
| 20 | `n_disputed_open` | Tagged sentences still waiting on adjudication. |
| 21 | `n_resolved` | Tagged sentences with a final decision. |
| 22 | `n_resolved_to_none` | Resolved sentences whose decision was 'no tag'. |
| 23 | `n_comments` | Adjudication comments on the filing. |

## Values

### Strength (Mitigation only)

| Value | Meaning |
|---|---|
| 1 | Below average: a commitment, intention, or plan to do it. |
| 2 | Average: claims to have implemented it, but vaguely or not explained. |
| 3 | Above average: lists specific steps or names a framework. |

### Taxonomy

**Risk**

- Legal: Ongoing Litigation, IP & Copyright, Compliance costs/burdens, Uncertainty & Complexity, Other
- Competitive: Investment Cost & Uncertainty, Market Share Uncertainty, Other
- Reputational: Individual or Organizational Reputation, Other
- Sociotechnical: Environmental, Malicious Actors / Misuse, Human-centered, Privacy & Security, Other
- AI Safety (General, Broad): (no subcategory; exported as `-`)

**Mitigation**

- Governance & Oversight: Board Structure & Oversight, Overall Risk Management & Governance Plan, Whistleblower Protections or Conflict of Interest Disclosures
- Environmental Impact: Environmental Impact Mitigation
- Societal Impact: Design for AI-Human Value Alignment, Societal Impact Assessment, Education / Public Goodwill
- Technical & Security Controls: AI Capabilities Safeguards, AI-Generated Content, AI Security, Privacy, and Data Protections
- Operational Process Controls: Testing & Auditing, System Access Management, Post-deployment Monitoring, Incident Monitoring, Response, and Recovery
- Transparency: System Documentation, Third-Party System Access for Assessment, User Rights & Recourse

**Responsible AI Commitment Statement**

- No category or subcategory (both exported as `-`).

## Things to know about the data

1. 381 filings have tags from one person only. On 153 of them every row is disputed because the second annotator marked the filing done with no tags. That is a real disagreement, not missing data.
2. 110 rows were resolved to "no tag" (`resolved_to_none` = true).
3. Baxter 2024 and 2025 (64 rows) were adjudicated in a Google Sheet before in-tool adjudication existed. Their `adjudicated_status` is blank.
4. 50 rows are exact duplicates (same person, same sentence, same tag twice). `annotation_id` tells them apart.
5. Same Mitigation tag with different strengths counts as agreed. `strength_disputed` flags it (5 sentences).
6. 241 two-person filings still have open disputes; 176 are fully done.
7. When one person tags a span of sentences and the other tags only some of them, the untagged sentences inside the span show as disputed in the adjudication report, even on a finalized filing. In `annotations.csv` the span is one row and counts as resolved once any of its sentences is. Workday 2025 has three such sentences (296 to 298).
8. Checked against the database on 2026-09-25: every annotation and every adjudication is in the export.

## Questions for you

1. The six annotators are Naomi, Yesenia, Akshitha, Amali, Joseline and Alexa. Anyone else who should be in?
2. Single-annotator filings: keep, flag, or separate?
3. Should different strengths count as a disagreement?
4. Baxter 2024 and 2025: enter the Sheet decisions into the tool, or leave blank?
5. Duplicate tags: drop them, or leave them for you to handle?
6. Any column to add, rename, or remove? Renaming later breaks anything already reading the file.
7. Should `year` be the fiscal year instead of the filing year?
8. Should a decision on a span tag count for every sentence in the span (see item 7 above)?
