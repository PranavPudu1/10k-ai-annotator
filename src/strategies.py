"""Registry of AI annotation methodologies.

Each Strategy defines how the 10-K text is chunked and which LLM is called.
The Streamlit version dropdown reads these via STRATEGIES.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str                    # internal description (kept for compat)
    description: str             # one paragraph, shown in the About expander
    chunker: str                 # function name registered in src.chunkers
    chunker_params: dict = field(default_factory=dict)
    model: str = "gpt-5.4-mini"
    display_label: str = ""      # what users see in the UI; falls back to name
    workflow: str = "chunked"    # "chunked" (chunker + LLM) or "sequential" (multi-phase)
    prompt_builder: str = "baseline"  # "baseline" or "hai_tuned"

    def label(self) -> str:
        return self.display_label or self.name


BASELINE_STRATEGY = Strategy(
    id="baseline",
    name="Original baseline (full doc, one call)",
    display_label="V0 — Original baseline (full doc, one call)",
    description=(
        "Send the entire 10-K text to gpt-5.4-mini in a single call. This is the "
        "method used for the 50-doc rollout — the model sees every sentence at "
        "once and decides which ones discuss AI risk or mitigation."
    ),
    chunker="full_doc",
)

KEYWORD_WINDOW_20_STRATEGY = Strategy(
    id="keyword_window_20",
    name="Keyword filter + ±20 sentence window",
    display_label="V1 — Keyword filter + ±20 sentence window",
    description=(
        "Filter sentences using a 195-term AI vocabulary. For each sentence "
        "containing an AI keyword, take a window of 20 sentences before and 20 "
        "sentences after. Overlapping windows are merged. Each merged window is "
        "sent as its own LLM call. Annotations from every chunk are aggregated "
        "and deduplicated by sentence."
    ),
    chunker="keyword_window",
    chunker_params={"window_sentences": 20},
)

KEYWORD_PER_SENTENCE_STRATEGY = Strategy(
    id="keyword_per_sentence",
    name="Keyword filter + per-sentence (no context)",
    display_label="V2 — Keyword filter + per-sentence (no context)",
    description=(
        "Filter sentences using the same AI vocabulary. Each matched sentence is "
        "sent to the LLM by itself with no neighbor context — one LLM call per "
        "matched sentence."
    ),
    chunker="keyword_per_sentence",
)

SEQUENTIAL_BATCHED_STRATEGY = Strategy(
    id="sequential_batched",
    name="Sequential 4-phase chain",
    display_label="V3 — Sequential 4-phase chain",
    description=(
        "Break the annotation task into four sequential LLM calls. Phase 1 lists "
        "candidate AI-relevant anchors over the full doc. Phase 2 decides each "
        "candidate's kind (Risk / Risk Mitigation / drop). Phase 3 assigns "
        "category + subcategory from the relevant taxonomy half. Phase 4 scores "
        "mitigation strength. Each phase sees the prior phase's verdicts as "
        "context. ~4 calls, ~30s per doc, mirrors the staged human MVP flow."
    ),
    chunker="full_doc",  # ignored when workflow == "sequential"
    workflow="sequential",
)

HAI_TUNED_ONESHOT_STRATEGY = Strategy(
    id="hai_tuned_oneshot",
    name="One-shot tuned on HAI feedback (v1 rules)",
    display_label="V4 — One-shot tuned on HAI feedback (v1 rules)",
    description=(
        "Same shape as baseline (one LLM call over the full doc) but the system "
        "prompt is augmented with 12 hand-distilled DON'T rules and a handful of "
        "few-shot exemplars drawn from Naomi and Angie's 876 graded annotations. "
        "The rules target the recurring failure modes: 'not specific to AI', "
        "duplicates, sentence fragments, and over-tagging on generic business "
        "language. v1 rules: distilled from the short-label distribution + small "
        "sample of long explanations."
    ),
    chunker="full_doc",
    prompt_builder="hai_tuned",
)

HAI_TUNED_ONESHOT_V2_STRATEGY = Strategy(
    id="hai_tuned_oneshot_v2",
    name="One-shot tuned on HAI feedback (v2 deep-read rules)",
    display_label="V4.1 — One-shot tuned on HAI feedback (v2 deep-read principles)",
    description=(
        "Same shape as V4 (one LLM call over the full doc with HAI-derived rules) "
        "but the rules were synthesized after a systematic read of all 844 reviewer "
        "verdicts. Principles-only — no subcategory-specific patches — to avoid "
        "overfitting to Naomi and Angie's specific Alphabet/Apple/Microsoft "
        "examples. The 15 principles cover what NOT to tag (over-tagging is 73% of "
        "reviewer flags), when to tag positively, and format-correctness "
        "requirements (no duplicates, no sentence fragments)."
    ),
    chunker="full_doc",
    prompt_builder="hai_tuned_v2",
)


SEQUENTIAL_PASSAGE_AWARE_STRATEGY = Strategy(
    id="sequential_passage_aware",
    name="Passage-aware sequential + HAI guardrails",
    display_label="V5 — Passage-aware sequential + HAI guardrails",
    description=(
        "Six-phase pipeline designed to fix the recall gap surfaced by missed-anchor "
        "analysis: humans tag sentences whose AI relevance comes from the surrounding "
        "passage, which V3 and V4.1 explicitly excluded. Phase 1 identifies AI-topic "
        "passages at section level. Phase 2 sweeps candidates from inside those "
        "passages PLUS direct AI mentions outside them. Phase 3 applies the HAI v3 "
        "guardrails to drop cybersecurity boilerplate, financial-management language, "
        "product descriptions, etc. Phases 4-6 do kind/category/strength. HAI v3 "
        "rules (deep-read principles minus the strict-context rule, plus passage-"
        "aware additions) are in the system prompt of every phase."
    ),
    chunker="full_doc",
    workflow="sequential_passage_aware",
    prompt_builder="hai_tuned_v3",
)


XML_COT_BASELINE_STRATEGY = Strategy(
    id="xml_cot_baseline",
    name="Baseline + XML `<Reasoning>` CoT",
    display_label="V6 — Baseline + XML `<Reasoning>` CoT",
    description=(
        "Same shape as V0 baseline (full doc, one call) but the annotation schema "
        "requires a `reasoning` field per annotation. The prompt asks the model to "
        "wrap its reasoning in literal `<Reasoning>...</Reasoning>` XML tags — the "
        "format the notes doc asks for. Each output annotation carries a "
        "chain-of-thought trace citing the words that pushed the decision."
    ),
    chunker="full_doc",
    prompt_builder="xml_cot",
)

N_SENTENCE_CHUNK_20_STRATEGY = Strategy(
    id="n_sentence_chunk_20",
    name="Fixed 20-sentence chunks (no keyword filter)",
    display_label="V7 — 20-sentence chunks",
    description=(
        "Slide a 20-sentence window across the full doc with stride 20 (non-"
        "overlapping). Each window becomes its own LLM call — the model tags "
        "everything inside. Answers the notes doc's option B: 'Split doc into "
        "chunks (e.g., N sentence chunks, maybe try 20, 40) – ask it to tag "
        "everything inside.' No keyword filter — every sentence is seen at least once."
    ),
    chunker="n_sentence",
    chunker_params={"n_sentences": 20},
)

N_SENTENCE_CHUNK_40_STRATEGY = Strategy(
    id="n_sentence_chunk_40",
    name="Fixed 40-sentence chunks (no keyword filter)",
    display_label="V8 — 40-sentence chunks",
    description=(
        "Same as V7 but the window is 40 sentences instead of 20. Half as many "
        "chunks, larger context per call. Direct comparison with V7 shows the "
        "chunk-size sensitivity of the tagging quality."
    ),
    chunker="n_sentence",
    chunker_params={"n_sentences": 40},
)


STRATEGIES: dict[str, Strategy] = {
    s.id: s for s in (
        BASELINE_STRATEGY,
        KEYWORD_WINDOW_20_STRATEGY,
        KEYWORD_PER_SENTENCE_STRATEGY,
        SEQUENTIAL_BATCHED_STRATEGY,
        HAI_TUNED_ONESHOT_STRATEGY,
        HAI_TUNED_ONESHOT_V2_STRATEGY,
        SEQUENTIAL_PASSAGE_AWARE_STRATEGY,
        XML_COT_BASELINE_STRATEGY,
        N_SENTENCE_CHUNK_20_STRATEGY,
        N_SENTENCE_CHUNK_40_STRATEGY,
    )
}


def get_strategy(strategy_id: str) -> Strategy:
    if strategy_id not in STRATEGIES:
        raise KeyError(f"unknown strategy {strategy_id!r}; known: {list(STRATEGIES)}")
    return STRATEGIES[strategy_id]
