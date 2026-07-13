"""Sequential 4-phase LLM workflow for the V3 strategy.

Phase 1 — Candidate identification: scan the full doc, return list of anchor_ids
         that discuss AI / ML / automated decision-making.
Phase 2 — Kind decision: for each candidate, decide Risk vs Risk Mitigation vs drop.
Phase 3 — Category + subcategory: for each kept candidate, pick from the
         relevant taxonomy half.
Phase 4 — Strength: for each mitigation, score 1/2/3 per the rubric.

The output is a flat list of annotations with the same shape as the baseline
pipeline emits (sentence, kind, category, subcategory, strength), so the rest
of the pipeline (validation, alignment) is unchanged.

The full chain caches as a list of {phase, raw_response} so partial reruns work.
"""
from __future__ import annotations
import json
from pathlib import Path

from .config import MAX_OUTPUT_TOKENS, MODEL, TIMEOUT_SECONDS
from .llm_call import _call_api, _parse_response


def _phase_schema(properties: dict, required: list[str]) -> dict:
    """Build a strict JSON schema that returns {"verdicts": [...]}."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdicts"],
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": required,
                    "properties": properties,
                },
            }
        },
    }


def _phase1_prompt() -> str:
    return """You are a corporate-disclosure analyst. The user message contains the full text
of a company's Form 10-K with sentences pre-numbered as `[s-NNNNN] <sentence>`.

Identify every sentence that discusses AI, machine learning, generative AI,
automated decision-making, or closely related concepts. Be inclusive but only
include sentences that are SPECIFICALLY about AI/ML — not generic business
sentences that mention AI in passing.

Return JSON `{"verdicts": [{"anchor_id": "s-NNNNN"}]}` listing each qualifying
anchor. Do not include kind, category, or any other field — that comes later.
"""


def _phase2_prompt() -> str:
    return """You are a corporate-disclosure analyst. The user message contains a numbered list
of sentences pre-selected as AI-related. For each one, decide whether it is:

- "Risk" — describes an AI-related risk consequence (regulatory, reputational,
  competitive, environmental, technical, etc.)
- "Risk Mitigation" — describes a specific AI-related mitigation action,
  governance practice, technical safeguard, etc.
- null — the sentence is not actually about an AI risk or mitigation. Drop it.

Return JSON `{"verdicts": [{"anchor_id": "s-NNNNN", "kind": "Risk" | "Risk Mitigation" | null}]}`.
"""


def _phase3_prompt(half_taxonomy_md: str, kind: str) -> str:
    return f"""You are a corporate-disclosure analyst. The user message contains a numbered list
of sentences already determined to be {kind}. Assign each one a category and
subcategory from the table below — exactly one (category, subcategory) per
annotation. A single sentence may produce multiple annotations if it expresses
multiple distinct (category, subcategory) pairs.

# {kind} taxonomy
{half_taxonomy_md}

Return JSON `{{"verdicts": [{{"anchor_id": "s-NNNNN", "category": "...", "subcategory": "..."}}]}}`.
"""


def _phase4_prompt(strength_rubric_md: str) -> str:
    return f"""You are a corporate-disclosure analyst. The user message contains a numbered list
of sentences already determined to be Risk Mitigations, with their category +
subcategory. Score each one 1, 2, or 3 per the rubric below.

# Strength rubric
{strength_rubric_md}

Return JSON `{{"verdicts": [{{"anchor_id": "s-NNNNN", "strength": 1 | 2 | 3}}]}}`.
"""


def _half_taxonomy_md(taxonomy: dict, kind: str) -> str:
    rows = taxonomy["risks"] if kind == "Risk" else taxonomy["mitigations"]
    header = "| Category | Subcategory | Description |\n|---|---|---|"
    body = "\n".join(
        f"| {r['category']} | {r['subcategory']} | {(r['description'] or '').replace(chr(10), ' ').strip()} |"
        for r in rows
    )
    return header + "\n" + body


def _strength_rubric_md(taxonomy: dict) -> str:
    return "\n".join(
        f"- **{r['strength']}** — {r['reason']}" for r in taxonomy["strength_rubric"]
    )


def _format_sentences(sentences: list[dict], anchor_ids: list[str] | None = None) -> str:
    """Render sentences as `[anchor_id] text` lines for the LLM input."""
    if anchor_ids is None:
        return "\n".join(f"[{s['anchor_id']}] {s['text']}" for s in sentences)
    by_id = {s["anchor_id"]: s["text"] for s in sentences}
    return "\n".join(f"[{a}] {by_id.get(a, '')}" for a in anchor_ids if a in by_id)


def _load_cache(cache_path: Path) -> dict[str, dict]:
    if not cache_path.exists():
        return {}
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    return {entry["phase"]: entry["raw_response"] for entry in raw}


def _write_cache(cache_path: Path, entries: dict[str, dict]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    out = [{"phase": k, "raw_response": v} for k, v in entries.items()]
    cache_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def _phase_call(
    phase_id: str,
    system_prompt: str,
    user_text: str,
    schema: dict,
    cache: dict[str, dict],
    cache_path: Path,
    refresh: bool,
) -> dict:
    if phase_id in cache and not refresh:
        print(f"[seq] {phase_id}: cached")
        raw = cache[phase_id]
    else:
        print(f"[seq] {phase_id}: calling {MODEL}", flush=True)
        raw = _call_api(system_prompt, user_text, schema)
        cache[phase_id] = raw
        _write_cache(cache_path, cache)
    return _parse_response(raw)


def run_sequential_batched(
    sentences: list[dict],
    taxonomy: dict,
    cache_path: Path,
    refresh: bool = False,
) -> list[dict]:
    """Run the 4-phase chain. Returns annotations in the baseline shape."""
    cache = {} if refresh else _load_cache(cache_path)
    by_id = {s["anchor_id"]: s["text"] for s in sentences}

    # Phase 1: candidate identification over full doc.
    p1_schema = _phase_schema(
        {"anchor_id": {"type": "string"}}, ["anchor_id"],
    )
    p1 = _phase_call(
        "p1_candidates",
        _phase1_prompt(),
        _format_sentences(sentences),
        p1_schema, cache, cache_path, refresh,
    )
    candidates = [v["anchor_id"] for v in p1.get("verdicts", []) if v.get("anchor_id") in by_id]
    print(f"[seq] phase 1 returned {len(candidates)} candidates")

    if not candidates:
        return []

    # Phase 2: kind decision per candidate.
    p2_schema = _phase_schema(
        {"anchor_id": {"type": "string"},
         "kind": {"type": ["string", "null"], "enum": ["Risk", "Risk Mitigation", None]}},
        ["anchor_id", "kind"],
    )
    p2 = _phase_call(
        "p2_kind",
        _phase2_prompt(),
        _format_sentences(sentences, candidates),
        p2_schema, cache, cache_path, refresh,
    )
    kept: list[tuple[str, str]] = []  # (anchor_id, kind)
    for v in p2.get("verdicts", []):
        aid = v.get("anchor_id")
        kind = v.get("kind")
        if aid in by_id and kind in ("Risk", "Risk Mitigation"):
            kept.append((aid, kind))
    print(f"[seq] phase 2 kept {len(kept)} of {len(candidates)} candidates")
    if not kept:
        return []

    risks = [aid for aid, k in kept if k == "Risk"]
    mits = [aid for aid, k in kept if k == "Risk Mitigation"]

    # Phase 3a: risks → category/subcategory.
    annotations: list[dict] = []
    p3_schema = _phase_schema(
        {"anchor_id": {"type": "string"},
         "category": {"type": "string"},
         "subcategory": {"type": "string"}},
        ["anchor_id", "category", "subcategory"],
    )
    if risks:
        p3a = _phase_call(
            "p3a_risk_cats",
            _phase3_prompt(_half_taxonomy_md(taxonomy, "Risk"), "Risk"),
            _format_sentences(sentences, risks),
            p3_schema, cache, cache_path, refresh,
        )
        for v in p3a.get("verdicts", []):
            aid = v.get("anchor_id")
            if aid not in by_id:
                continue
            annotations.append({
                "sentence": by_id[aid],
                "kind": "Risk",
                "category": v.get("category", ""),
                "subcategory": v.get("subcategory", ""),
                "strength": None,
            })

    # Phase 3b + Phase 4: mitigations → category/subcategory + strength.
    if mits:
        p3b = _phase_call(
            "p3b_mit_cats",
            _phase3_prompt(_half_taxonomy_md(taxonomy, "Risk Mitigation"), "Risk Mitigation"),
            _format_sentences(sentences, mits),
            p3_schema, cache, cache_path, refresh,
        )
        mit_cards = []
        for v in p3b.get("verdicts", []):
            aid = v.get("anchor_id")
            if aid not in by_id:
                continue
            mit_cards.append({
                "anchor_id": aid,
                "sentence": by_id[aid],
                "category": v.get("category", ""),
                "subcategory": v.get("subcategory", ""),
            })

        if mit_cards:
            mit_anchors = [c["anchor_id"] for c in mit_cards]
            p4_schema = _phase_schema(
                {"anchor_id": {"type": "string"},
                 "strength": {"type": "integer", "enum": [1, 2, 3]}},
                ["anchor_id", "strength"],
            )
            p4 = _phase_call(
                "p4_strength",
                _phase4_prompt(_strength_rubric_md(taxonomy)),
                _format_sentences(sentences, mit_anchors),
                p4_schema, cache, cache_path, refresh,
            )
            strength_by = {v.get("anchor_id"): v.get("strength") for v in p4.get("verdicts", [])}
            for c in mit_cards:
                annotations.append({
                    "sentence": c["sentence"],
                    "kind": "Risk Mitigation",
                    "category": c["category"],
                    "subcategory": c["subcategory"],
                    "strength": strength_by.get(c["anchor_id"]),
                })

    print(f"[seq] returning {len(annotations)} annotations (R: {sum(1 for a in annotations if a['kind']=='Risk')}, M: {sum(1 for a in annotations if a['kind']=='Risk Mitigation')})")
    return annotations
