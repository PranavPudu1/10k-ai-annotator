# HAI-derived principles (v3, passage-aware)

Derived from the v2 deep-read of 844 reviewer verdicts (Naomi + Angie),
adjusted for V5's passage-aware sequential workflow. The key change from
v2: the strict "AI Term must be in adjacent paragraph" rule is **dropped**
because V5's Phase 1 identifies AI-topic passages at section level, so the
adjacency test happens at a different layer of the pipeline. A new
positive principle replaces it.

These rules are designed to be applied **inside every phase** of the V5
chain (passage identification, candidate sweep, context filter, kind,
category, strength).

---

## What NOT to tag

1. **The sentence's central claim must be ABOUT AI, not merely mention AI.**
   A sentence that lists AI alongside other items, names an AI product in
   passing, or invokes "AI" as a generic example is not annotation-worthy.
   Both reviewers wrote variations of "If stretched, the statement fits the
   risks/mitigation categories, but is not AI-specific enough" — that
   stretching test is the decisive signal to drop.

2. **A description of AI is not a risk or a mitigation.** Marketing or
   product-feature language about AI-powered offerings (e.g. an AI
   assistant, an AI-augmented browser, an AI accelerator, "AI Solutions")
   does not describe a risk consequence and does not describe a mitigation
   action. Reviewers repeatedly flagged these as "more about products
   themselves than actual responsible AI or AI risks." A risk sentence
   must say what could go wrong; a mitigation sentence must say what
   action is being taken to prevent or address an AI-specific harm.

3. **A business decision to invest in or partner around AI is not, by itself,
   a risk or mitigation.** Sentences like "we are expanding our investment
   in AI", "we have a partnership with OpenAI", "we are integrating AI into
   our products" describe corporate strategy. To qualify as a tag, the
   sentence must additionally describe an uncertain return, a specific
   capability concern, a risk consequence, or a corresponding safeguard.

4. **Cybersecurity, privacy, and data-governance language is not an AI
   mitigation unless the sentence itself explicitly scopes the practice to
   AI systems, AI training data, AI model outputs, or AI deployment.**
   "Our cybersecurity program protects users", "we maintain an information
   security program", "the Audit Committee oversees cybersecurity risk",
   "we conduct penetration testing" — none of these are AI mitigations.
   This is the most common over-tagging mode in the corpus. The reviewers
   reached an explicit consensus and used the phrase "Based off of our
   conversation regarding whether cybersecurity actually counts when it's
   not AI related, I would not highlight this" many dozens of times. Even
   when a candidate sits inside an AI-topic passage from Phase 1, apply
   this rule strictly — cybersecurity boilerplate is the most frequent
   false positive.

5. **Financial risk management language is never an AI annotation.**
   Foreign-exchange hedging, derivatives, currency forwards, credit-default
   swaps, fixed-income diversification, cash-flow hedges, interest-rate
   risk, portfolio diversification — all are categorically outside the
   taxonomy. They frequently get mis-tagged under "Risk Management &
   Governance Plan"; do not tag them.

6. **General enterprise risk management, board oversight, and audit
   committee language is not an AI mitigation unless the sentence itself
   names AI as the specific risk being overseen.** Generic statements
   about ERM programs, internal audit, executive risk responsibility, or
   board cybersecurity oversight do not qualify. The taxonomy is asking
   about governance practices specific to AI.

7. **A specific date, fact, or regulation-summary statement is not a risk
   disclosure.** A sentence that just states when a regulation came into
   force (e.g. "The EU AI Act came into force on August 1, 2024"), or
   describes a specific non-AI litigation event, is not a risk —
   the sentence must describe a risk *consequence* or mitigation *action*.

8. **AI used as an internal business-metrics tool is not in scope.**
   Sentences describing internal use of machine learning to estimate user
   counts, compute engagement metrics, or calibrate survey data are about
   business measurement, not about AI affecting users or society. The
   taxonomy targets AI in products and systems that act on people
   externally.

9. **A sentence about AI is not automatically about Responsible AI.**
   Even when AI is the subject, the sentence may describe AI as a market
   opportunity, a competitive position, or a product capability without
   raising a responsible-AI concern. The sentence must align with a Risk
   or Mitigation in the taxonomy (legal, competitive, reputational,
   sociotechnical, governance & oversight, etc.), not just describe an AI
   product.

## When to tag

10. **NEW for V5 — A sentence that sits inside an AI-topic passage and
    describes a downstream consequence can be tagged even if it does not
    itself contain the word "AI".** This replaces v2's strict "AI Term
    must be in adjacent paragraph" rule. The Phase 1 passage_summary is
    your context anchor — when the passage is genuinely about AI
    regulation, AI environmental impact, AI-driven content quality, AI
    governance, etc., tag the consequence sentences (regulatory
    uncertainty, business impact, mitigation responses) even when they
    use generic legal/business/governance language. The reviewers
    explicitly noted this pattern: "we weren't tagging context broadly
    enough" appeared dozens of times as a Human Miss rationale.

11. **Tag when AI/ML/automation is the explicit subject AND the sentence
    states a risk consequence or a mitigation action.** Example shapes
    the reviewers consistently said should have been tagged:

    - "There are significant risks involved in developing and deploying
      AI and there can be no assurance that the usage of AI will enhance
      our products or services or be beneficial to our business..."
    - "AI technology and services are highly competitive, rapidly
      evolving, and require significant investment..."
    - "demand for our products such as our custom AI accelerators or XPUs
      and other AI-related products may be reduced..."
    - "Our AI initiatives also depend on our access to data to
      effectively train our models."

    Do not skip these as "too general" — the reviewers explicitly said
    "I have no idea why Chibudom and I didn't tag this one - it fits
    perfectly."

## Subcategory specificity

12. **Use "Investment Cost & Uncertainty" only when the sentence
    describes AI-specific investment cost, return uncertainty, or capex.**
    Generic business investment language about "significant investment"
    or "may not be commercially viable" does not qualify unless the
    investment is specifically about AI.

13. **Use "Market Share Uncertainty" only when the sentence explicitly
    describes one of these three:** (a) pressure from an AI development
    race, (b) fear of falling behind on AI, or (c) loss of market share
    due to AI competition. Generic competitive language does not qualify.

14. **Use "Governance & Oversight / Overall Risk Management & Governance
    Plan" only when the sentence describes a governance practice
    specifically scoped to AI — not generic ERM, board oversight, or
    audit committee language.**

## Format-correctness rules

15. **Each annotation's `sentence` field must be a complete sentence as
    it appears in the document.** Do not annotate fragments cut off in
    mid-clause. Do not split one logical sentence across multiple
    annotations.

16. **Do not emit the same `(sentence, kind, category, subcategory)`
    combination more than once.** If a single sentence expresses two
    distinct (category, subcategory) tags, emit two annotations — one
    per distinct pair — but never the same tuple twice.

## Default

17. **When the AI relevance is ambiguous AND the candidate is not
    inside a clearly AI-focused passage from Phase 1, prefer NOT to tag.**
    Over-tagging accounts for ~73% of all reviewer flags in this corpus;
    under-tagging is ~27%. The passage signal from Phase 1 is what
    distinguishes "borderline, default to skip" from "in an AI section,
    lean toward keep."
