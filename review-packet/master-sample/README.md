# Master CSV sample (for review)

Three finished filings in the proposed single "master" layout. This is a sample to review before the layout is applied to every filing; nothing else in the repo has changed.

## Files

| File | What it is |
|---|---|
| `master-sample-3-filings.xlsx` | The three filings as sheets, plus a `Columns` sheet. Start here. |
| `ServiceNow-Inc-2026_master.csv` | 163 sentences (33 tagged, 130 untagged keyword sentences) |
| `Workday-Inc-2025_master.csv` | 104 sentences (31 tagged, 73 untagged keyword sentences) |
| `MARSH-MCLENNAN-COMPANIES-INC-2024_master.csv` | 58 sentences (18 tagged, 40 untagged keyword sentences) |
| `CHECKS.md` | What was verified on each file, with counts |

The CSVs are UTF-8. If you open one in Excel by double-clicking, `·` shows as `¬∑`; use the workbook, or import with Data > From Text/CSV.

## How to read it

- One row is one final tag on one sentence. A sentence with two final tags has two rows; a sentence with no final tag has one row with the `official_` columns blank. Keep `tag_row = 1` for one row per sentence.
- `tagged = true` means at least one annotator tagged the sentence. `tagged = false` means it is here only because it contains a keyword and nobody tagged it.
- Read a row left to right: the sentence, the official tag, what each annotator originally tagged, where they disagreed, and how it was settled.
- Only finished filings are included: two annotators, both done, adjudication marked done in the tool.

## How Angie's requests were met

| # | Request | In the file |
|---|---|---|
| 1 | One row per final tag | Yes; `tag_row` numbers them |
| 2 | Official type, category, subcategory, strength | `official_type`, `official_category`, `official_subcategory`, `official_strength` |
| 3a | Agreed from the start: use that tag; both left it untagged: blank | Yes. If both gave the same Mitigation tag with different strengths and nobody decided, strength is blank |
| 3b | Disputed and resolved: use the resolved tag; resolved to no tag: blank | Yes |
| 4 | `sentence_disputed`, `type_disputed`, `category_disputed`, `subcategory_disputed` | Yes, as a ladder: each one being true makes the next ones true |
| 5 | Keyword sentences both annotators left untagged | Yes, all of them (`tagged = false`) |
| 6–7 | `has_ai_keyword`, `matched_keywords` | Yes, as whole-word matches |
| 8 | `group_id` | Yes |
| 9–10 | Context sentence numbers and text | Yes |
| 11 | `adjudication_comments` | Yes |

Added beyond the request: `tagged`, `tag_row`, `annotator_a_notes`, `annotator_b_notes`.

## Questions

1. **Untagged rows.** Many are there only because of "cybersecurity" or "data center", which are on the keyword list (37 of 40 on Marsh & McLennan), and some are headings or table-of-contents lines such as "Cybersecurity 32". Keep all, keep only sentences with an AI term, or drop the non-sentences?
2. **Section labels.** In some filings the Cybersecurity section is labelled "Item 1B - Unresolved Staff Comments" (26 rows in Workday 2025). Should the export correct it?
3. **Undecided strength.** Where both gave the same Mitigation tag with different strengths and nobody adjudicated, `official_strength` is blank. How should those be settled?
4. **Keyword list.** "ML" also matches Maiden Lane and 1-month LIBOR; "A.I." matched a director's initials. Change the list?
5. **Anything missing?** Sentences with no keyword that nobody tagged are not in this file; they are planned as a separate all-sentences file.

## Columns

| Column | Meaning |
|---|---|
| `doc_id` | Filing id in the tool. Joins to filings.csv. |
| `cik` | The company's SEC id, 10 digits. |
| `company` | Company name. |
| `year` | Filing year. |
| `accession` | SEC accession number of the 10-K. |
| `section_name` | The 10-K section the sentence is in. |
| `sentence_ordinal` | Sentence number within the filing. One sentence per row, always. |
| `sentence_text` | The sentence. |
| `tagged` | true if at least one annotator tagged this sentence. false means it is here only because it contains a keyword and nobody tagged it. Not the same as having a final tag: a sentence one person tagged that was adjudicated to 'no tag' is tagged = true with n_final_tags = 0. |
| `official_type` | The final tag on this row: Risk, Mitigation, or Responsible AI Commitment Statement. Blank if the sentence has no final tag. |
| `official_category` | Category of the final tag. '-' for Commitment tags. Blank if no final tag. |
| `official_subcategory` | Subcategory of the final tag. '-' for Commitment tags and for AI Safety (General, Broad). Blank if no final tag. |
| `official_strength` | 1 to 3, Mitigation tags only. Blank if the two annotators gave different strengths and nobody decided between them (strength_disputed is then true). |
| `has_ai_keyword` | true if the sentence contains a keyword from the team's keyword list as a whole word. This is what the annotation page highlights. The list includes 'Cybersecurity' and 'Data center', which are not AI terms. |
| `matched_keywords` | The keywords found, separated by '; '. |
| `group_id` | Id of the multi-sentence tag(s) this sentence is part of, separated by '; '. Blank if every tag on it covers this sentence alone. |
| `context_sentence_ordinals` | Sentence numbers an annotator attached as extra context to a tag on this sentence. Different sets are separated by ' \| '. |
| `context_sentence_text` | Text of those context sentences, in the same order. |
| `final_tags` | All final tags on the sentence, separated by '; '. The same on every row of the sentence. |
| `final_source` | How the final tags came about: agreed (both gave the same tags), resolved (decided in adjudication), resolved_to_none (decided: no tag), resolved_span (decided on another sentence of the same multi-sentence tag), untagged (has an AI keyword, neither annotator tagged it), solo (single-annotator filing: that person's tags stand), pending (still disputed; should not occur on a finished filing). |
| `n_final_tags` | How many final tags the sentence has. The sentence has that many rows (one row if 0). |
| `tag_row` | Which of the sentence's rows this is, starting at 1. Keep tag_row = 1 to get one row per sentence. |
| `annotator_a` | First annotator (alphabetical). |
| `annotator_a_tags` | Their original tags on this sentence, separated by '; '. A multi-sentence tag appears on every sentence it covers. |
| `annotator_a_notes` | Their notes on those tags, separated by ' \| '. |
| `annotator_b` | Second annotator. Blank on single-annotator filings. |
| `annotator_b_tags` | Their original tags on this sentence. |
| `annotator_b_notes` | Their notes on those tags. |
| `sentence_disputed` | true if only one of the two annotators tagged the sentence. |
| `type_disputed` | true if the two did not give the same set of types (Risk / Mitigation / Commitment). Always true when sentence_disputed is true. |
| `category_disputed` | true if the two did not give the same set of type + category. Always true when type_disputed is true. |
| `subcategory_disputed` | true if the two did not give exactly the same set of tags, so this means 'any disagreement'. Always true when category_disputed is true. Strength and notes do not count. |
| `strength_disputed` | true if both gave the same Mitigation tag with different strengths. The five _disputed columns are blank on single-annotator filings. |
| `span_ordinals` | First and last sentence number of the multi-sentence tag(s) this sentence is part of. |
| `adjudication_comments` | The adjudication discussion on this sentence, as 'Name (time): text', separated by ' \| '. |
| `resolved_by` | Who recorded the final decision. Blank if no decision was needed. |
| `resolved_at` | When the final decision was recorded (UTC). |
| `n_comments` | Number of adjudication comments on this sentence. |
| `filing_finalized` | true if adjudication of the filing was marked done. false only on single-annotator filings, which need none. |
| `adjudication_done_at` | When adjudication was marked done (UTC). |
| `archived` | true if the filing has been archived. |
