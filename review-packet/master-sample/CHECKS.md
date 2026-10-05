# Master CSV sample: what was checked

Three finished filings in the new master layout, built from production data as of 2026-10-05.
This is a sample for review: the tool and the daily exports in this repo are unchanged.

| File | Sentences in the filing | Sentences in the file | Tagged | Untagged keyword sentences | Rows |
|---|---|---|---|---|---|
| `ServiceNow-Inc-2026_master.csv` | 3,650 | 163 | 33 | 130 | 180 |
| `Workday-Inc-2025_master.csv` | 2,815 | 104 | 31 | 73 | 106 |
| `MARSH-MCLENNAN-COMPANIES-INC-2024_master.csv` | 672 | 58 | 18 | 40 | 62 |

`master-sample-3-filings.xlsx` holds the same three files as sheets, plus a `Columns` sheet with the meaning of all 41 columns.
Open the workbook in Excel; the CSVs are UTF-8 and Excel shows `·` as `¬∑` if a CSV is double-clicked.

## All three filings are finished (checked in production)

| | ServiceNow 2026 | Workday 2025 | Marsh & McLennan 2024 |
|---|---|---|---|
| Adjudication marked done | 2026-09-30 | 2026-09-22 | 2026-10-05 |
| Both annotators marked done | yes (Naomi Ichiriu, Yesenia Garcia) | yes (Amali Oakley, Joseline Viveros) | yes (Amali Oakley, Joseline Viveros) |
| Sentences where the two disagreed | 28 | 23 | 13 |
| Of those with a recorded decision | 28 | 23 (3 via another sentence of the same multi-sentence tag) | 13 |
| Decisions still open | 0 | 0 | 0 |
| Rows with `final_source = pending` | 0 | 0 | 0 |

## Nothing stored for these filings is missing from the files

Compared directly against the database, without going through the export code.

| Stored in the tool | ServiceNow 2026 | Workday 2025 | Marsh & McLennan 2024 |
|---|---|---|---|
| Original tags, each in the right annotator's column on the right sentence | 67 of 67 | 50 of 50 | 36 of 36 |
| Tags in the file that are not in the database | 0 | 0 | 0 |
| Annotator notes | none written | 4 of 4 | 7 of 7 |
| Multi-sentence tag ids | 12 of 12 | 6 of 6 | 2 of 2 |
| Context-sentence links | none made | 5 of 5 | 2 of 2 |
| Adjudication decisions (final tags, who, when) | 28 of 28 | 22 of 22 | 14 of 14 |
| Adjudication comments (author and text) | 30 of 30 | 29 of 29 | 26 of 26 |
| Sentence text equals the filing's sentence at that number | 163 of 163 | 104 of 104 | 58 of 58 |
| Keyword sentences in the filing = sentences flagged in the file | 160 = 160 | 98 = 98 | 56 = 56 |

## Automated checks on each file (24, all passed on all three)

Every check re-derives the value independently instead of trusting the export.

1. Header is the 41 documented columns in order; `(doc_id, sentence_ordinal, tag_row)` is unique.
2. Each sentence has `max(1, n_final_tags)` rows numbered by `tag_row`; every other column is identical across a sentence's rows.
3. `tagged` is true exactly when an annotator tagged the sentence, and false exactly when `final_source` is `untagged`.
4. `final_tags` equals the `official_*` columns of the sentence's rows joined together; `official_*` are blank exactly when there is no final tag; no final tag repeats.
5. Every official tag and every original annotator tag exists in the taxonomy; strength is 1–3 and only on Mitigation.
6. The five `_disputed` flags equal a recomputation from `annotator_a_tags` and `annotator_b_tags`, and the ladder holds (sentence ⇒ type ⇒ category ⇒ subcategory).
7. `final_source` is consistent with everything else: `agreed` only when both gave the same tags and those are the final tags; `resolved` / `resolved_to_none` / `resolved_span` always carry `resolved_by` and `resolved_at`; `untagged` only when neither tagged and the sentence has a keyword.
8. `has_ai_keyword` matches `matched_keywords`, and every listed keyword is in the sentence as a whole word.
9. Comments, spans, context sentences and notes are internally consistent; the filing columns are constant.
10. Reconciled with the older exports: original tags and notes against `annotations.csv`, final tags and `resolved_by/at` against `final_labels.csv`, counts against `filings.csv`. Workday was also reconciled against the GitHub review packet from 2026-09-25.

## What the untagged rows contain

The untagged rows are Angie's item 5: sentences with a keyword that neither annotator tagged. The checks above confirm they are complete and accurate. They do not judge whether a row is useful, and many are not about AI.

| | ServiceNow 2026 | Workday 2025 | Marsh & McLennan 2024 |
|---|---|---|---|
| Untagged rows | 130 | 73 | 40 |
| There only because of "cybersecurity" or "data center" (both are on the keyword list) | 40 | 48 | 37 |
| Not a sentence: a heading, table-of-contents line, table cell or signature line | 8 | 8 | 5 |

## Things to know when reading the rows

- **ServiceNow 2026 and Workday 2025 are archived, so their untagged sentences were rebuilt.** Archiving deletes a filing's untagged sentences. They were recovered by re-parsing the source 10-K, and the result was accepted only because it reproduces the saved data exactly: the same sentence count, and every tag on the same sentence number with the same text.
- **`category_disputed` can be true when both chose the same category.** The flags compare the full set of tags. On Workday sentence 352 both gave Risk · Reputational, and A also gave Risk · Legal, so the sets differ at category level.
- **A sentence in a multi-sentence tag can be decided on a neighbour.** Workday sentences 296–298 show `resolved_span`: only A tagged them (as part of the tag over 294–299), and the decision was recorded on sentence 294.
- **Some section labels are wrong.** 26 Workday rows say "Item 1B - Unresolved Staff Comments" but are the Cybersecurity section; the tool has always stored that filing this way.
