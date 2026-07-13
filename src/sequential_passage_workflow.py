"""V5 passage-aware sequential workflow.

Six phases:
  P1 — Passage identification: find AI-topic spans across the full doc.
  P2 — Candidate sweep: union of (anchors in P1 passages) + (direct AI
       mentions outside P1 passages).
  P3 — HAI-guarded context filter: per candidate, decide keep/drop given
       the sentence + passage_summary + ±8 sentence context window.
  P4 — Kind decision: Risk / Risk Mitigation / drop.
  P5 — Category + subcategory.
  P6 — Strength (mitigations only).

All phases share the same HAI v3 rules + taxonomy context in their system
prompt. Each phase's raw_response is cached individually so partial reruns
work.
"""
from __future__ import annotations
import json
from pathlib import Path

from .config import DATA_DIR, MODEL
from .llm_call import _call_api, _parse_response


_HAI_V3_RULES_PATH = DATA_DIR / "hai_dont_rules_v3.md"


def _load_rules() -> str:
    return _HAI_V3_RULES_PATH.read_text(encoding="utf-8").strip()


def _phase_schema(properties: dict, required: list[str], list_name: str = "verdicts") -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [list_name],
        "properties": {
            list_name: {
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


def _format_sentences(sentences: list[dict], anchor_ids: list[str] | None = None) -> str:
    if anchor_ids is None:
        return "\n".join(f"[{s['anchor_id']}] {s['text']}" for s in sentences)
    by_id = {s["anchor_id"]: s["text"] for s in sentences}
    return "\n".join(f"[{a}] {by_id.get(a, '')}" for a in anchor_ids if a in by_id)


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
        print(f"[v5-seq] {phase_id}: cached")
        raw = cache[phase_id]
    else:
        print(f"[v5-seq] {phase_id}: calling {MODEL}", flush=True)
        raw = _call_api(system_prompt, user_text, schema)
        cache[phase_id] = raw
        _write_cache(cache_path, cache)
    return _parse_response(raw)


def _phase1_prompt(rules_md: str) -> str:
    return f"""You are a corporate-disclosure analyst reading a Form 10-K. Sentences are
pre-numbered as `[s-NNNNN] <sentence>`.

Your job in this phase: identify CONTIGUOUS PASSAGES where AI, ML, generative
AI, automated decision-making, or related concepts are the CENTRAL topic of
the discussion. A passage is a span of consecutive sentences focused on AI
risk, AI mitigation, AI regulation, AI products/business strategy, AI
environmental impact, AI-driven content quality, or AI governance.

For each passage, return:
- start_anchor (first sentence of the passage)
- end_anchor (last sentence of the passage)
- topic_summary (1 sentence describing what AI risk or mitigation theme the
  passage covers, e.g. "Discussion of EU AI Act and global AI regulation
  uncertainty" or "Mitigation of AI training infrastructure environmental
  impact via data-center efficiency gains")

Be inclusive when including sentences that don't themselves mention AI but
are CONSEQUENCES, RESPONSES, or DOWNSTREAM IMPACTS of AI-focused discussion
in adjacent sentences. Be EXCLUSIVE about passages that are about
cybersecurity, financial risk management, generic enterprise risk
management, or non-AI litigation — those are not AI passages even if a
company also makes AI products.

# Guardrails (apply when deciding passage boundaries)
{rules_md}

Return JSON `{{"passages": [{{"start_anchor": "s-NNNNN", "end_anchor": "s-NNNNN", "topic_summary": "..."}}]}}`.
"""


def _phase2_prompt(rules_md: str) -> str:
    return f"""You are a corporate-disclosure analyst. The user message lists sentences from
a 10-K that are OUTSIDE any AI-topic passage already identified by an
earlier phase. Find any sentences that directly mention AI, ML, generative
AI, or automated decision-making — but be selective. A sentence merely
listing AI alongside other items, or naming an AI product without a risk
or mitigation framing, should NOT be returned.

# Guardrails
{rules_md}

Return JSON `{{"verdicts": [{{"anchor_id": "s-NNNNN"}}]}}` listing the
qualifying anchors.
"""


def _phase3_prompt(rules_md: str) -> str:
    return f"""You are a corporate-disclosure analyst. The user message lists candidate
sentences with their surrounding ±8 sentence context window and (when
available) the topic_summary of the AI-topic passage they sit inside.

Your job: decide which candidates to KEEP for downstream classification as
Risk or Risk Mitigation. For each candidate:

- KEEP if it describes a specific AI-related risk consequence or mitigation
  action, OR sits inside an AI-topic passage and describes a downstream
  consequence flowing from that passage's theme.
- DROP if it is cybersecurity / privacy / data-governance boilerplate not
  scoped to AI.
- DROP if it is financial-risk management language (forex, derivatives,
  hedging, credit, cash flow).
- DROP if it is generic enterprise risk management, board oversight, audit
  committee language not scoped to AI.
- DROP if it is a marketing or product description of an AI product
  without a risk/mitigation framing.
- DROP if it is a date, fact, or regulation-summary statement without a
  risk consequence.
- DROP if it is just a corporate strategy statement ("we are investing in
  AI") without a risk/mitigation framing.

# Guardrails (apply rigorously)
{rules_md}

Return JSON `{{"verdicts": [{{"anchor_id": "s-NNNNN", "keep": true, "reason": "..."}}]}}`
for every candidate. Include `reason` as a 1-sentence justification.
"""


def _phase4_prompt(rules_md: str) -> str:
    return f"""You are a corporate-disclosure analyst. The user message contains sentences
already filtered as AI-relevant candidates. For each one, decide:

- "Risk" — describes an AI-related risk consequence (regulatory, reputational,
  competitive, environmental, technical, etc.)
- "Risk Mitigation" — describes a specific AI-related mitigation action,
  governance practice, or technical safeguard.
- null — on second look, this is not actually about an AI risk or
  mitigation. Drop it.

# Guardrails
{rules_md}

Return JSON `{{"verdicts": [{{"anchor_id": "s-NNNNN", "kind": "Risk" | "Risk Mitigation" | null}}]}}`.
"""


def _phase5_prompt(rules_md: str, half_taxonomy_md: str, kind: str) -> str:
    return f"""You are a corporate-disclosure analyst. The user message lists sentences
already determined to be {kind}. Assign each one a category and
subcategory from the table below. A single sentence may produce multiple
annotations if it expresses multiple distinct (category, subcategory)
pairs — but never emit the same (category, subcategory) tuple twice.

# {kind} taxonomy
{half_taxonomy_md}

# Guardrails (especially subcategory specificity)
{rules_md}

Return JSON `{{"verdicts": [{{"anchor_id": "s-NNNNN", "category": "...", "subcategory": "..."}}]}}`.
"""


def _phase6_prompt(rules_md: str, strength_rubric_md: str) -> str:
    return f"""You are a corporate-disclosure analyst. The user message lists Risk
Mitigation sentences with their category and subcategory. Score each one
1, 2, or 3 per the rubric.

# Strength rubric
{strength_rubric_md}

# Guardrails
{rules_md}

Return JSON `{{"verdicts": [{{"anchor_id": "s-NNNNN", "strength": 1 | 2 | 3}}]}}`.
"""


def _format_p3_input(candidates: list[str], sentences: list[dict], passage_by_anchor: dict[str, str]) -> str:
    """Build the user message for Phase 3: each candidate gets sentence + passage_summary + context window."""
    by_id = {s["anchor_id"]: s["text"] for s in sentences}
    sentence_idx = {s["anchor_id"]: i for i, s in enumerate(sentences)}
    chunks: list[str] = []
    for aid in candidates:
        if aid not in by_id:
            continue
        idx = sentence_idx[aid]
        lo = max(0, idx - 8)
        hi = min(len(sentences) - 1, idx + 8)
        context_lines = []
        for j in range(lo, hi + 1):
            prefix = ">>" if sentences[j]["anchor_id"] == aid else "  "
            context_lines.append(f"{prefix} [{sentences[j]['anchor_id']}] {sentences[j]['text']}")
        summary = passage_by_anchor.get(aid, "(no passage)")
        chunks.append(
            f"### CANDIDATE {aid}\n"
            f"passage_summary: {summary}\n"
            f"context_window:\n" + "\n".join(context_lines)
        )
    return "\n\n".join(chunks)


def run_sequential_passage_aware(
    sentences: list[dict],
    taxonomy: dict,
    cache_path: Path,
    refresh: bool = False,
) -> list[dict]:
    cache = {} if refresh else _load_cache(cache_path)
    by_id = {s["anchor_id"]: s["text"] for s in sentences}
    anchor_order = {s["anchor_id"]: i for i, s in enumerate(sentences)}
    rules_md = _load_rules()

    # Phase 1: Passage identification.
    p1_schema = _phase_schema(
        {
            "start_anchor": {"type": "string"},
            "end_anchor": {"type": "string"},
            "topic_summary": {"type": "string"},
        },
        ["start_anchor", "end_anchor", "topic_summary"],
        list_name="passages",
    )
    p1 = _phase_call(
        "p1_passages",
        _phase1_prompt(rules_md),
        _format_sentences(sentences),
        p1_schema, cache, cache_path, refresh,
    )
    passages = [p for p in p1.get("passages", []) if p.get("start_anchor") in anchor_order and p.get("end_anchor") in anchor_order]
    print(f"[v5-seq] phase 1 identified {len(passages)} AI-topic passages")

    # Phase 2: Candidate sweep.
    # 2a — sentences inside any P1 passage (no LLM call).
    in_passage: dict[str, str] = {}  # anchor_id -> topic_summary
    for p in passages:
        start, end = anchor_order[p["start_anchor"]], anchor_order[p["end_anchor"]]
        if end < start:
            start, end = end, start
        for i in range(start, end + 1):
            in_passage[sentences[i]["anchor_id"]] = p["topic_summary"]
    # 2b — direct AI mentions outside any passage (one LLM call).
    outside = [s for s in sentences if s["anchor_id"] not in in_passage]
    p2_schema = _phase_schema({"anchor_id": {"type": "string"}}, ["anchor_id"])
    direct_mentions: list[str] = []
    if outside:
        p2 = _phase_call(
            "p2_outside_mentions",
            _phase2_prompt(rules_md),
            _format_sentences(outside),
            p2_schema, cache, cache_path, refresh,
        )
        direct_mentions = [v["anchor_id"] for v in p2.get("verdicts", []) if v.get("anchor_id") in by_id]
    candidates = sorted(set(in_passage.keys()) | set(direct_mentions), key=lambda a: anchor_order[a])
    print(f"[v5-seq] phase 2 candidate set: {len(in_passage)} from passages + {len(direct_mentions)} direct mentions = {len(candidates)} unique")

    if not candidates:
        return []

    # Phase 3: HAI-guarded context filter.
    p3_schema = _phase_schema(
        {
            "anchor_id": {"type": "string"},
            "keep": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        ["anchor_id", "keep", "reason"],
    )
    p3 = _phase_call(
        "p3_context_filter",
        _phase3_prompt(rules_md),
        _format_p3_input(candidates, sentences, in_passage),
        p3_schema, cache, cache_path, refresh,
    )
    kept_after_filter: list[str] = []
    for v in p3.get("verdicts", []):
        aid = v.get("anchor_id")
        if aid in by_id and v.get("keep"):
            kept_after_filter.append(aid)
    print(f"[v5-seq] phase 3 kept {len(kept_after_filter)} of {len(candidates)} candidates after HAI filter")

    if not kept_after_filter:
        return []

    # Phase 4: Kind decision.
    p4_schema = _phase_schema(
        {"anchor_id": {"type": "string"},
         "kind": {"type": ["string", "null"], "enum": ["Risk", "Risk Mitigation", None]}},
        ["anchor_id", "kind"],
    )
    p4 = _phase_call(
        "p4_kind",
        _phase4_prompt(rules_md),
        _format_sentences(sentences, kept_after_filter),
        p4_schema, cache, cache_path, refresh,
    )
    risks = []
    mits = []
    for v in p4.get("verdicts", []):
        aid = v.get("anchor_id")
        if aid not in by_id:
            continue
        if v.get("kind") == "Risk":
            risks.append(aid)
        elif v.get("kind") == "Risk Mitigation":
            mits.append(aid)
    print(f"[v5-seq] phase 4: {len(risks)} risks, {len(mits)} mitigations kept (of {len(kept_after_filter)})")

    annotations: list[dict] = []
    p5_schema = _phase_schema(
        {
            "anchor_id": {"type": "string"},
            "category": {"type": "string"},
            "subcategory": {"type": "string"},
        },
        ["anchor_id", "category", "subcategory"],
    )

    # Phase 5a: Risk categories.
    if risks:
        p5a = _phase_call(
            "p5a_risk_cats",
            _phase5_prompt(rules_md, _half_taxonomy_md(taxonomy, "Risk"), "Risk"),
            _format_sentences(sentences, risks),
            p5_schema, cache, cache_path, refresh,
        )
        for v in p5a.get("verdicts", []):
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

    # Phase 5b + Phase 6: Mitigation categories + strength.
    if mits:
        p5b = _phase_call(
            "p5b_mit_cats",
            _phase5_prompt(rules_md, _half_taxonomy_md(taxonomy, "Risk Mitigation"), "Risk Mitigation"),
            _format_sentences(sentences, mits),
            p5_schema, cache, cache_path, refresh,
        )
        mit_cards = []
        for v in p5b.get("verdicts", []):
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
            p6_schema = _phase_schema(
                {"anchor_id": {"type": "string"},
                 "strength": {"type": "integer", "enum": [1, 2, 3]}},
                ["anchor_id", "strength"],
            )
            p6 = _phase_call(
                "p6_strength",
                _phase6_prompt(rules_md, _strength_rubric_md(taxonomy)),
                _format_sentences(sentences, [c["anchor_id"] for c in mit_cards]),
                p6_schema, cache, cache_path, refresh,
            )
            strength_by = {v.get("anchor_id"): v.get("strength") for v in p6.get("verdicts", [])}
            for c in mit_cards:
                annotations.append({
                    "sentence": c["sentence"],
                    "kind": "Risk Mitigation",
                    "category": c["category"],
                    "subcategory": c["subcategory"],
                    "strength": strength_by.get(c["anchor_id"]),
                })

    print(f"[v5-seq] returning {len(annotations)} annotations")
    return annotations
