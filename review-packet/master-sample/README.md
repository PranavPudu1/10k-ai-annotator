# Master CSV sample (for review)

A sample of the proposed single "master" file, to review before it is applied to every filing.

## What's in here

One workbook: `master-sample-3-filings.xlsx`. It has four sheets:

| Sheet | What it is |
|---|---|
| `ServiceNow 2026` | 163 sentences: 33 tagged, 130 keyword sentences nobody tagged |
| `Workday 2025` | 104 sentences: 31 tagged, 73 keyword sentences nobody tagged |
| `Marsh McLennan 2024` | 58 sentences: 18 tagged, 40 keyword sentences nobody tagged |
| `Columns` | What each of the 41 columns means |

All three filings are finished: both annotators done and adjudication marked done.

One row is one final tag on one sentence. Read a row left to right: the sentence, the official tag, what each annotator originally tagged, where they disagreed, and how it was settled.

## Angie's requests and how they were met

| # | Request | In the file |
|---|---|---|
| 1 | One row per final tag | Yes |
| 2 | Official type, category, subcategory, strength | `official_type`, `official_category`, `official_subcategory`, `official_strength` |
| 3 | Agreed: use that tag. Resolved: use the resolved tag. No tag: blank | Yes |
| 4 | `sentence_disputed`, `type_disputed`, `category_disputed`, `subcategory_disputed` | Yes, true/false |
| 5 | Keyword sentences both annotators left untagged | Yes, all of them |
| 6–7 | `has_ai_keyword`, `matched_keywords` | Yes |
| 8 | `group_id` | Yes |
| 9–10 | Context sentence numbers and text | Yes |
| 11 | `adjudication_comments` | Yes |

## Other columns added

| Column | Why |
|---|---|
| `tagged` | true if at least one annotator tagged the sentence; false if it is here only because of a keyword |
| `tag_row` | 1 for a sentence's first row, 2 for its second final tag, and so on; keep `tag_row = 1` for one row per sentence |
| `annotator_a_notes`, `annotator_b_notes` | Each annotator's notes on their tags |

## Questions

1. **Untagged rows.** Many are there only because "cybersecurity" and "data center" are on the keyword list (37 of 40 on Marsh & McLennan), and some are headings such as "Cybersecurity 32". Keep all, keep only sentences with an AI term, or drop the non-sentences?
2. **Section labels.** Some filings label the Cybersecurity section "Item 1B - Unresolved Staff Comments" (26 rows in Workday 2025). Should the export correct it?
3. **Undecided strength.** Where both gave the same Mitigation tag with different strengths and nobody adjudicated, `official_strength` is blank. How should those be settled?
4. **Keyword list.** "ML" also matches Maiden Lane and 1-month LIBOR. Change the list?
5. **Anything missing?** Sentences with no keyword that nobody tagged are not in this file; they are planned as a separate all-sentences file.
