# HAI-derived DON'T rules

Distilled from 844 reviewer verdicts (Naomi + Angie) on the baseline AI's
annotations across all 10 companies' 2024 10-Ks. The dominant failure
modes from `Explanation` short labels:

- 499 — Not specific to AI
- 43 — Duplicate annotation
- 40 — Not specific to RESPONSIBLE AI
- 15 — Sentence fragment
- 13 — Subcategory wrong
- 212 — Human Miss (the AI was right — humans should have tagged it)

Rules below are written for the LLM as the consumer.

---

1. **Do NOT tag a sentence solely because it contains the word "AI" or "machine learning" in passing.** The sentence must be ABOUT an AI risk or AI mitigation, not merely mention AI as part of a list or generic example. A sentence like "we expand our investment in AI across the company" is not enough — it must describe a specific risk consequence or a specific mitigation action.

2. **Do NOT tag generic business or financial statements that happen to mention AI.** Phrases like "secure by default", "privacy by design", "responsible data handling", or "we invest in technology" are not AI-specific mitigations unless the sentence explicitly ties them to AI systems.

3. **Do NOT emit duplicate annotations for the same sentence.** Each (sentence, kind, category, subcategory) combination must appear at most once in your output. If a single sentence describes multiple distinct risks, emit one annotation per distinct (category, subcategory) — but never the same tuple twice.

4. **Do NOT tag partial sentence fragments.** The `sentence` field in your output must be a complete sentence as it appears in the document, ending at a sentence boundary. Do not split a sentence across multiple annotations and do not annotate clause fragments.

5. **Do NOT use "Investment Cost & Uncertainty" unless the sentence is explicitly about AI-specific investment costs, returns, or capex.** Generic business risk language about "significant investment", "may not be commercially viable", or "adequate return of capital" does not qualify unless it is specifically about AI.

6. **Do NOT use "Market Share Uncertainty" unless the sentence explicitly describes one of these three:** (a) pressure from an AI development race, (b) fear of falling behind on AI, or (c) loss of market share due to AI competition. Generic competitive language does not qualify.

7. **Do NOT tag a sentence that describes cybersecurity, privacy, or data-governance practices in general as a Risk Mitigation unless the sentence explicitly ties those practices to AI systems, AI training data, AI outputs, or AI deployment.** "Our cybersecurity program protects users" is not an AI mitigation; "our cybersecurity program includes safeguards for AI training data" is.

8. **Do NOT use "Governance & Oversight / Overall Risk Management & Governance Plan" for general enterprise risk management programs.** It must describe a governance practice specifically scoped to AI.

9. **Do NOT tag sentences that describe a risk to RESPONSIBLE AI principles in a generic way (fairness, ethics, transparency, accountability) without an explicit tie to a specific AI risk or mitigation action.** Mentioning "responsible AI" by itself is not enough.

10. **Do tag sentences where AI/ML/automation is the explicit subject and the sentence describes a consequence or response.** Example shapes the model should look for: "AI may cause...", "AI could lead to...", "we mitigate AI risks by...", "to address AI-related concerns, we have...". These are the clearest signals — do not skip them as "too general".

11. **Do tag sentences describing AI training data, model behavior, generative AI outputs, or AI-specific governance — even if they do not use the exact word "risk" or "mitigation".** The taxonomy applies to descriptive statements about AI deployment, not just to sentences that use those exact words.

12. **When in doubt, prefer to NOT tag.** The most frequent reviewer complaint is over-tagging on sentences that mention AI but aren't actually about an AI risk or mitigation. If the AI relevance is ambiguous, leave it out.
