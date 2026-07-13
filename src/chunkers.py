"""Chunking strategies for the AI annotation pipeline.

Each chunker is a pure function:
    chunk(sentences, hits, params) -> list[Chunk]

where a Chunk is:
    {
        "chunk_id": str,                # e.g. "chunk_0001"
        "sentence_indices": list[int],  # contiguous indices into sentences.json
        "first_anchor": str,
        "last_anchor": str,
        "text": str,                    # the chunk's text, ready to send to the LLM
    }

The pipeline feeds each chunk to the LLM with the same taxonomy system prompt
and aggregates annotations across chunks (deduped on sentence content).
"""
from __future__ import annotations


def _make_chunk(chunk_num: int, sentences: list[dict], indices: list[int]) -> dict:
    sub = [sentences[i] for i in indices]
    return {
        "chunk_id": f"chunk_{chunk_num:04d}",
        "sentence_indices": indices,
        "first_anchor": sub[0]["anchor_id"],
        "last_anchor": sub[-1]["anchor_id"],
        "text": "\n".join(s["text"] for s in sub),
    }


def full_doc_chunker(sentences: list[dict], hits: list[dict], params: dict) -> list[dict]:
    """One chunk = the whole document. Ignores `hits`."""
    indices = list(range(len(sentences)))
    if not indices:
        return []
    return [_make_chunk(0, sentences, indices)]


def keyword_window_chunker(sentences: list[dict], hits: list[dict], params: dict) -> list[dict]:
    """For each hit, take [idx-window, idx+window]. Merge overlapping windows."""
    window = int(params.get("window_sentences", 20))
    if not hits or not sentences:
        return []

    n = len(sentences)
    # Build raw [lo, hi] ranges (inclusive), clamped to [0, n-1].
    ranges = []
    for hit in hits:
        i = int(hit["sentence_idx"])
        lo = max(0, i - window)
        hi = min(n - 1, i + window)
        ranges.append((lo, hi))

    # Sort + merge overlapping.
    ranges.sort()
    merged: list[list[int]] = []
    for lo, hi in ranges:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])

    chunks = []
    for k, (lo, hi) in enumerate(merged):
        indices = list(range(lo, hi + 1))
        chunks.append(_make_chunk(k, sentences, indices))
    return chunks


def keyword_per_sentence_chunker(sentences: list[dict], hits: list[dict], params: dict) -> list[dict]:
    """One chunk per matched sentence — no context. Hits already deduped by sentence."""
    chunks = []
    for k, hit in enumerate(hits):
        i = int(hit["sentence_idx"])
        chunks.append(_make_chunk(k, sentences, [i]))
    return chunks


_REGISTRY = {
    "full_doc": full_doc_chunker,
    "keyword_window": keyword_window_chunker,
    "keyword_per_sentence": keyword_per_sentence_chunker,
}


def chunk_for_strategy(strategy_chunker: str, sentences: list[dict], hits: list[dict], params: dict) -> list[dict]:
    if strategy_chunker not in _REGISTRY:
        raise KeyError(f"unknown chunker {strategy_chunker!r}; known: {list(_REGISTRY)}")
    return _REGISTRY[strategy_chunker](sentences, hits, params)
