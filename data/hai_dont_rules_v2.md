# HAI-derived principles (v2, deep-read)

Distilled from a systematic read of 844 reviewer verdicts produced by Naomi
and Angie on the baseline AI annotator's output across all 10 companies'
2024 10-Ks. Source distribution:

- 499 — Not specific to AI         (over-tagging, by far the biggest mode)
- 212 — Human Miss                  (the AI was right, humans should have tagged it)
-  43 — Duplicate annotation
-  40 — Not specific to RESPONSIBLE AI
-  15 — Sentence fragment
-  13 — AI tagged subcategory incorrectly
-  22 — other / smaller groups

These are PRINCIPLES, not subcategory-specific patches, so they generalize
to docs and companies the reviewers never saw. Verbatim reviewer language
is cited where it captures the principle better than a paraphrase.

---

## What NOT to tag

1. **The sentence's central claim must be ABOUT AI, not merely mention AI.**
   A sentence that lists AI alongside other items, names an AI product in
   passing, or invokes "AI" as a generic example is not annotation-worthy.
   Both reviewers wrote variations of "If stretched, the statement fits the
   risks/mitigation categories, but is not AI-specific enough" — that
   stretching test is the decisive signal to drop.

2. **If neither the sentence itself nor the immediately surrounding paragraph
   uses an AI/ML/automation term, do not tag.** Naomi's most-repeated
   justification was "an AI Term was not present in the paragraph before and
   after." Use the local paragraph (the sentence and the ones immediately
   adjacent) as the context window for establishing AI relevance.

3. **A description of AI is not a risk or a mitigation.** Marketing or
   product-feature language about AI-powered offerings (e.g. an AI
   assistant, an AI-augmented browser, an AI accelerator, "AI Solutions")
   does not describe a risk consequence and does not describe a mitigation
   action. Reviewers repeatedly flagged these as "more about products
   themselves than actual responsible AI or AI risks." A risk sentence
   must say what could go wrong; a mitigation sentence must say what
   action is being taken to prevent or address an AI-specific harm.

4. **A business decision to invest in or partner around AI is not, by itself,
   a risk or mitigation.** Sentences like "we are expanding our investment
   in AI", "we have a partnership with OpenAI", "we are integrating AI into
   our products" describe corporate strategy. To qualify as a tag, the
   sentence must additionally describe an uncertain return, a specific
   capability concern, a risk consequence, or a corresponding safeguard.

5. **Cybersecurity, privacy, and data-governance language is not an AI
   mitigation unless the sentence itself explicitly scopes the practice to
   AI systems, AI training data, AI model outputs, or AI deployment.**
   "Our cybersecurity program protects users", "we maintain an information
   security program", "the Audit Committee oversees cybersecurity risk",
   "we conduct penetration testing" — none of these are AI mitigations.
   This is the most common over-tagging mode in the corpus. The reviewers
   reached an explicit consensus on this and used the phrase "Based off of
   our conversation regarding whether cybersecurity actually counts when
   it's not AI related, I would not highlight this" many dozens of times.
   Be conservative.

6. **Financial risk management language is never an AI annotation.**
   Foreign-exchange hedging, derivatives, currency forwards, credit-default
   swaps, fixed-income diversification, cash-flow hedges, interest-rate
   risk, portfolio diversification — all are categorically outside the
   taxonomy. They frequently get mis-tagged under "Risk Management &
   Governance Plan"; do not tag them.

7. **General enterprise risk management, board oversight, and audit
   committee language is not an AI mitigation unless the sentence itself
   names AI as the specific risk being overseen.** Generic statements
   about ERM programs, internal audit, executive risk responsibility, or
   board cybersecurity oversight do not qualify. The taxonomy is asking
   about governance practices specific to AI.

8. **Generic legal, regulatory, or litigation language is not an AI risk
   unless AI/ML/automation is explicitly named as the regulated subject.**
   "We are subject to laws and regulations", "we may face legal proceedings",
   boilerplate compliance text, and references to specific non-AI litigation
   (antitrust, DMA, GDPR enforcement, FTC consent orders, IP infringement)
   do not become AI risks just because the company also makes AI products.
   Likewise, a date or fact statement about a regulation (e.g. "The EU AI
   Act came into force on August 1, 2024") is not a risk disclosure —
   the sentence must describe a risk consequence or mitigation action.

9. **AI used as an internal business-metrics tool is not in scope.**
   Sentences describing internal use of machine learning to estimate user
   counts, compute engagement metrics, or calibrate survey data are about
   business measurement, not about AI affecting users or society. The
   taxonomy targets AI in products and systems that act on people
   externally.

10. **A sentence about AI is not automatically about Responsible AI.**
    Even when AI is the subject, the sentence may describe AI as a market
    opportunity, a competitive position, or a product capability without
    raising a responsible-AI concern. The 40 records labelled "Not specific
    to RESPONSIBLE AI" caught exactly this pattern — Tesla's Optimus
    humanoid robot, NVIDIA's AI architecture overview, Oracle's SaaS
    product descriptions. The sentence must align with a Risk or Mitigation
    in the taxonomy (legal, competitive, reputational, sociotechnical,
    governance & oversight, etc.), not just describe an AI product.

## When to tag

11. **Tag when AI/ML/automation is the explicit subject AND the sentence
    states a risk consequence or a mitigation action.** Example shapes the
    reviewers consistently said should have been tagged:

    - "There are significant risks involved in developing and deploying
      AI and there can be no assurance that the usage of AI will enhance
      our products or services or be beneficial to our business..."
    - "AI technology and services are highly competitive, rapidly
      evolving, and require significant investment..."
    - "demand for our products such as our custom AI accelerators or XPUs
      and other AI-related products may be reduced..."
    - "Our AI initiatives also depend on our access to data to
      effectively train our models."

    These were "Human Miss" cases that the AI got right. Do not skip them
    as "too general"; the reviewers explicitly said "I have no idea why
    Chibudom and I didn't tag this one - it fits perfectly."

12. **When AI is the topic of a contiguous passage, tag the sentences
    that contribute risk or mitigation content even if they do not
    themselves repeat the word "AI".** Reviewers repeatedly noted "This
    was context right before something Chibudom and I tagged — I think
    we weren't tagging context broadly enough." When the surrounding
    paragraph establishes AI as the topic and a sentence describes a
    specific risk or mitigation action, tag the sentence — but only if
    rule #2's context window actually establishes AI as the topic.

## Format-correctness rules (not classification — output structure)

13. **Each annotation's `sentence` field must be a complete sentence as
    it appears in the document.** Do not annotate fragments cut off in
    mid-clause. Do not split one logical sentence across multiple
    annotations.

14. **Do not emit the same `(sentence, kind, category, subcategory)`
    combination more than once.** If a single sentence expresses two
    distinct (category, subcategory) tags, emit two annotations — one
    per distinct pair — but never the same tuple twice.

## Default

15. **When the AI relevance is ambiguous, prefer NOT to tag.**
    Over-tagging accounts for ~73% of all reviewer flags in this corpus;
    under-tagging is ~27%. False positives are the dominant failure mode
    and the most costly one to fix at review time.
