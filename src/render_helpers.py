"""Pure rendering helpers shared by the Streamlit app and the static-site build.

Two-coder aware: human cards carry `coder` ("A"|"B") and `coder_name`.
Document highlights use the anchor_source value from align.py:
  ai             -> AI only
  coder_a        -> Coder A only
  coder_b        -> Coder B only
  coders_both    -> Both coders agree, no AI
  ai_and_a       -> AI + Coder A
  ai_and_b       -> AI + Coder B
  ai_and_both    -> AI + both coders
"""
from __future__ import annotations

import re


_SOURCE_CLASS_MAP = {
    "ai":          "source-ai",
    "coder_a":     "source-coder-a",
    "coder_b":     "source-coder-b",
    "coders_both": "source-coders-both",
    "ai_and_a":    "source-ai-and-a",
    "ai_and_b":    "source-ai-and-b",
    "ai_and_both": "source-ai-and-both",
}


def build_paragraphs(text: str, sentences: list[dict], anchor_sources: dict) -> list[list[dict]]:
    """Walk the document by char offset, slicing into paragraphs at blank-line
    boundaries. Each paragraph is a list of tokens — annotated sentence spans
    (is_sentence=True) interleaved with plain text gaps.
    """
    boundaries: list[tuple[int, int]] = []
    para_re = re.compile(r"\n{2,}")
    cursor = 0
    for m in para_re.finditer(text):
        if m.start() > cursor:
            boundaries.append((cursor, m.start()))
        cursor = m.end()
    if cursor < len(text):
        boundaries.append((cursor, len(text)))

    paragraphs: list[list[dict]] = []
    s_idx = 0
    n_sentences = len(sentences)

    for p_start, p_end in boundaries:
        tokens: list[dict] = []
        cur = p_start
        while s_idx < n_sentences and sentences[s_idx]["char_start"] < p_end:
            s = sentences[s_idx]
            s_start = s["char_start"]
            s_end = s["char_end"]
            if s_end <= p_start:
                s_idx += 1
                continue
            if s_start >= p_end:
                break
            local_start = max(s_start, p_start)
            local_end = min(s_end, p_end)
            if local_start > cur:
                tokens.append({"is_sentence": False, "text": text[cur:local_start]})
            source = anchor_sources.get(s["anchor_id"])
            tokens.append({
                "is_sentence": True,
                "anchor_id": s["anchor_id"],
                "text": text[local_start:local_end],
                "source_class": _SOURCE_CLASS_MAP.get(source, ""),
            })
            cur = local_end
            s_idx += 1
        if cur < p_end:
            tokens.append({"is_sentence": False, "text": text[cur:p_end]})
        if tokens:
            paragraphs.append(tokens)

    return paragraphs


def build_cards(side_cards_by_anchor: dict, sentences: list[dict], side: str) -> list[dict]:
    """Return a flat list of cards with anchor_id for the template, in document order.

    `side` is "ai" for AI cards or "human" for human cards. Human cards retain
    their `coder` and `coder_name` so the template can color them per coder.
    """
    items: list[tuple[int, str, dict]] = []
    sentence_order = {s["anchor_id"]: i for i, s in enumerate(sentences)}
    for anchor_id, sides in side_cards_by_anchor.items():
        order = sentence_order.get(anchor_id, 10**9)
        for c in sides.get(side, []):
            items.append((order, anchor_id, c))
    items.sort(key=lambda t: t[0])
    out = []
    for _, anchor_id, c in items:
        out.append({**c, "anchor_id": anchor_id})
    return out


def build_annotations_rows(aligned: dict, sentences: list[dict]) -> list[dict]:
    """Flatten every annotation (AI + human, matched + unmatched) into a list of
    dicts for the All Annotations view. Sorted by document order, then source.
    """
    sentence_text_by_anchor = {s["anchor_id"]: s["text"] for s in sentences}
    sentence_order = {s["anchor_id"]: i for i, s in enumerate(sentences)}

    rows: list[dict] = []

    def _push(anchor_id: str | None, c: dict) -> None:
        if anchor_id and anchor_id in sentence_text_by_anchor:
            sentence_text = sentence_text_by_anchor[anchor_id]
        else:
            sentence_text = c.get("sentence_excerpt", "")
        subcat = c.get("subcategory")
        if not subcat or subcat == "-":
            subcat = c.get("category", "")
        if c.get("side") == "ai":
            source = "AI"
            coder = "AI"
        else:
            coder = c.get("coder") or ""
            name = c.get("coder_name") or ""
            source = "Human"
            if coder and name:
                coder = f"{coder} — {name}"
            elif coder:
                coder = coder
            else:
                coder = "Human"
        rows.append({
            "Source": source,
            "Coder": coder,
            "Anchor ID": anchor_id or "(unmatched)",
            "Sentence": (sentence_text or "")[:120],
            "Type": c.get("kind", ""),
            "Category": c.get("category", ""),
            "Subcategory": subcat,
            "Strength": c.get("strength") if c.get("kind") == "Risk Mitigation" else None,
            "_order": sentence_order.get(anchor_id, 10**9),
        })

    for anchor_id, sides in aligned["cards_by_anchor"].items():
        for c in sides.get("ai", []):
            _push(anchor_id, c)
        for c in sides.get("human", []):
            _push(anchor_id, c)
    for c in aligned.get("unmatched_ai", []):
        _push(None, c)
    for c in aligned.get("unmatched_human", []):
        _push(None, c)

    rows.sort(key=lambda r: (r["_order"], r["Source"], r["Coder"]))
    for r in rows:
        del r["_order"]
    return rows


def _legend_html(coder_a_name: str, coder_b_name: str) -> str:
    """Build the legend explaining card and color semantics.

    Coder names come from the per-doc human DataFrame (so 'A — Naomi' /
    'B — Chibudom' adapts when other sections use different names).
    """
    a_label = f"A {('— ' + coder_a_name) if coder_a_name else ''}".strip()
    b_label = f"B {('— ' + coder_b_name) if coder_b_name else ''}".strip()

    return f"""
<style>
  .legend-wrapper {{
    font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
    color: var(--text-color, #e5e7eb);
    padding: 4px 4px 12px 4px;
  }}
  .legend-wrapper .intro {{
    font-size: 13px;
    margin: 0 0 12px 0;
    line-height: 1.5;
    color: inherit;
    opacity: 0.9;
  }}
  .legend-wrapper .card-row {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
    max-width: 720px;
    margin: 0 auto 18px auto;
  }}
  .legend-wrapper .lcard {{
    padding: 8px 10px;
    border-radius: 6px;
    background: white;
    border: 1px solid #e7e5e4;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    font-size: 12px;
    line-height: 1.35;
    color: #1c1917;
  }}
  .legend-wrapper .lcard.ai      {{ border-left: 3px solid #2563eb; }}
  .legend-wrapper .lcard.coder-a {{ border-left: 3px solid #ea580c; }}
  .legend-wrapper .lcard.coder-b {{ border-left: 3px solid #9333ea; }}
  .legend-wrapper .lpill {{
    display: inline-block;
    padding: 1px 6px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 600;
    margin-right: 4px;
    vertical-align: 1px;
    color: white;
  }}
  .legend-wrapper .lpill.ai      {{ background: #2563eb; }}
  .legend-wrapper .lpill.coder-a {{ background: #ea580c; }}
  .legend-wrapper .lpill.coder-b {{ background: #9333ea; }}
  .legend-wrapper .lkind {{ font-weight: 600; color: #44403c; }}
  .legend-wrapper .lcat  {{ color: #44403c; }}
  .legend-wrapper .lsub  {{ color: #1c1917; font-weight: 500; margin-top: 2px; }}
  .legend-wrapper .swatches {{
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(128, 128, 128, 0.25);
    font-size: 12px;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 6px 16px;
    max-width: 880px;
    margin: 12px auto 0 auto;
    color: inherit;
    opacity: 0.9;
  }}
  .legend-wrapper .swatch {{
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 2px;
    vertical-align: -1px;
    margin-right: 6px;
  }}
  .legend-wrapper .swatch.ai          {{ background: rgba(37, 99, 235, 0.18); border: 1px solid #2563eb; }}
  .legend-wrapper .swatch.coder-a     {{ background: rgba(234, 88, 12, 0.18); border: 1px solid #ea580c; }}
  .legend-wrapper .swatch.coder-b     {{ background: rgba(147, 51, 234, 0.18); border: 1px solid #9333ea; }}
  .legend-wrapper .swatch.coders-both {{ background: rgba(13, 148, 136, 0.20); border: 1px solid #0d9488; }}
  .legend-wrapper .swatch.ai-and-a    {{ background: rgba(22, 163, 74, 0.20); border: 1px solid #16a34a; }}
  .legend-wrapper .swatch.ai-and-b    {{ background: rgba(8, 145, 178, 0.20); border: 1px solid #0891b2; }}
  .legend-wrapper .swatch.ai-and-both {{ background: rgba(202, 138, 4, 0.20); border: 1px solid #ca8a04; }}
</style>
<div class="legend-wrapper">
  <p class="intro">
    Each labeled sentence gets a card. AI is on the left;
    Coder A and Coder B (the two humans who annotated this doc) are on the right.
  </p>
  <div class="card-row">
    <div class="lcard ai">
      <div><span class="lpill ai">AI</span><span class="lkind">Risk Mitigation</span></div>
      <div class="lsub">Governance &amp; Oversight</div>
    </div>
    <div class="lcard coder-a">
      <div><span class="lpill coder-a">{a_label}</span><span class="lkind">Risk Mitigation</span></div>
      <div class="lsub">Governance &amp; Oversight</div>
    </div>
    <div class="lcard coder-b">
      <div><span class="lpill coder-b">{b_label}</span><span class="lkind">Risk Mitigation</span></div>
      <div class="lsub">Governance &amp; Oversight</div>
    </div>
  </div>
  <div class="swatches">
    <span><span class="swatch ai"></span>AI only</span>
    <span><span class="swatch coder-a"></span>{a_label} only</span>
    <span><span class="swatch coder-b"></span>{b_label} only</span>
    <span><span class="swatch coders-both"></span>Both coders agreed (no AI)</span>
    <span><span class="swatch ai-and-a"></span>AI + Coder A</span>
    <span><span class="swatch ai-and-b"></span>AI + Coder B</span>
    <span><span class="swatch ai-and-both"></span>AI + both coders</span>
  </div>
</div>
"""


# Keep the export name LEGEND_HTML for backward compatibility with existing
# imports (Streamlit app + static build); callers that have per-doc coder
# names should call `_legend_html(a_name, b_name)` directly.
LEGEND_HTML = _legend_html("", "")


def legend_for_doc(coder_a_name: str, coder_b_name: str) -> str:
    """Public helper for callers that have per-doc coder names."""
    return _legend_html(coder_a_name, coder_b_name)
