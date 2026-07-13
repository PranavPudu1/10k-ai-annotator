"""Build the LLM system prompt and JSON schema from taxonomy/strength/assumptions.

GROUND TRUTH FIREWALL: this module reads taxonomy.csv, strength.csv, and
assumptions.csv only. It NEVER reads the human ground truth CSV. The human
labels are display-only and must not leak into the prompt.
"""
from __future__ import annotations
import json


def _row_md(category: str, subcategory: str, description: str) -> str:
    desc = description.replace("\n", " ").strip()
    return f"| {category} | {subcategory} | {desc} |"


def _table(rows: list[dict]) -> str:
    header = "| Category | Subcategory | Description |\n|---|---|---|"
    body = "\n".join(_row_md(r["category"], r["subcategory"], r["description"]) for r in rows)
    return header + "\n" + body


def build_system_prompt(taxonomy: dict) -> str:
    risk_table = _table(taxonomy["risks"])
    mit_table = _table(taxonomy["mitigations"])
    strength_lines = "\n".join(
        f"- **{r['strength']}** — {r['reason']}" for r in taxonomy["strength_rubric"]
    )
    assumption_lines = "\n".join(f"- {a}" for a in taxonomy["assumptions"])

    return f"""You are a corporate-disclosure analyst. The user message contains the full text
of a company's Form 10-K. Your task is to identify sentences that describe an
AI-related **risk** or **risk mitigation**, and label each one against the
fixed taxonomy below.

# Output
Return JSON of the form `{{"annotations": [...]}}` where each item is:
- `sentence`: the verbatim sentence from the 10-K — copied exactly, character for character. Do not paraphrase or normalize whitespace/quotes.
- `kind`: either `"Risk"` or `"Risk Mitigation"`.
- `category`: one of the categories from the relevant taxonomy table below.
- `subcategory`: one of the subcategories listed under that category in the table.
- `strength`: integer 1, 2, or 3 when `kind == "Risk Mitigation"`. `null` when `kind == "Risk"`.

A sentence that contains multiple risks, multiple mitigations, or a mix should
appear as multiple entries — one per (kind, category, subcategory) it expresses.
Sentences with neither a risk nor a mitigation should NOT appear in the output.

# Risk taxonomy
{risk_table}

# Risk Mitigation taxonomy
{mit_table}

# Strength rubric (mitigations only; risks must have `strength: null`)
{strength_lines}

# Coding rules
{assumption_lines}

# Constraints
- Only label sentences that explicitly discuss AI, machine learning, generative AI, automated decision-making, or closely related concepts. Skip generic business-risk sentences.
- Do not include a rationale, explanation, or any field other than the five listed above.
- Do not emit commentary outside the JSON.
- If no sentence applies, return `{{"annotations": []}}`.
- Use only categories and subcategories that appear in the tables above. Do not invent new ones.
"""


def build_json_schema(taxonomy: dict) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["annotations"],
        "properties": {
            "annotations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["sentence", "kind", "category", "subcategory", "strength"],
                    "properties": {
                        "sentence": {"type": "string"},
                        "kind": {"type": "string", "enum": ["Risk", "Risk Mitigation"]},
                        "category": {"type": "string", "enum": taxonomy["all_categories"]},
                        "subcategory": {"type": "string", "enum": taxonomy["all_subcategories"]},
                        "strength": {"type": ["integer", "null"], "enum": [1, 2, 3, None]},
                    },
                },
            }
        },
    }


def build_hai_tuned_prompt(taxonomy: dict, rules_path=None, examples_block: str = "") -> str:
    """Augment the baseline prompt with HAI-derived DON'T rules + few-shot examples."""
    from pathlib import Path
    from .config import DATA_DIR

    base = build_system_prompt(taxonomy)
    if rules_path is None:
        rules_path = DATA_DIR / "hai_dont_rules.md"
    rules_md = Path(rules_path).read_text(encoding="utf-8").strip()

    parts = [base, "", "# Common failure modes (do NOT do these)", "", rules_md]
    if examples_block:
        parts += ["", "# Examples (from prior reviewer feedback)", "", examples_block]
    return "\n".join(parts)


if __name__ == "__main__":
    from .taxonomy import load_taxonomy

    tax = load_taxonomy()
    prompt = build_system_prompt(tax)
    schema = build_json_schema(tax)
    print(prompt[:1200])
    print("---")
    print(f"prompt length: {len(prompt):,} chars")
    print(f"schema enum sizes: categories={len(schema['properties']['annotations']['items']['properties']['category']['enum'])}, subcategories={len(schema['properties']['annotations']['items']['properties']['subcategory']['enum'])}")
