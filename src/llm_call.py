"""Single OpenAI call. Caches the raw SDK response to disk."""
from __future__ import annotations
import json
from pathlib import Path

from openai import OpenAI

from .config import MODEL, MAX_OUTPUT_TOKENS, TIMEOUT_SECONDS


class LLMTruncated(RuntimeError):
    pass


class LLMRefused(RuntimeError):
    pass


def _call_api(system_prompt: str, user_text: str, schema: dict) -> dict:
    client = OpenAI(timeout=TIMEOUT_SECONDS)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "annotations_payload",
                "schema": schema,
                "strict": True,
            },
        },
        extra_body={"max_completion_tokens": MAX_OUTPUT_TOKENS},
    )
    return response.model_dump()


def _parse_response(raw: dict) -> dict:
    choice = raw["choices"][0]
    finish_reason = choice.get("finish_reason")
    message = choice.get("message", {})
    refusal = message.get("refusal")
    content = message.get("content")

    if refusal:
        raise LLMRefused(f"Model refused: {refusal}")
    if finish_reason == "length":
        raise LLMTruncated(
            f"finish_reason=length — raise MAX_OUTPUT_TOKENS in src/config.py "
            f"(currently {MAX_OUTPUT_TOKENS})"
        )
    if not content:
        raise RuntimeError(f"No content in response (finish_reason={finish_reason})")
    return json.loads(content)


def call_model(
    system_prompt: str,
    user_text: str,
    schema: dict,
    cache_path: Path,
    refresh: bool = False,
) -> dict:
    """Run one chat completion. Cache to disk so demo restarts don't re-bill."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not refresh:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"[llm_call] using cached response at {cache_path}")
    else:
        print(f"[llm_call] calling {MODEL} (max_completion_tokens={MAX_OUTPUT_TOKENS})")
        raw = _call_api(system_prompt, user_text, schema)
        cache_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[llm_call] cached raw response to {cache_path}")
    return _parse_response(raw)


def call_model_per_chunk(
    chunks: list[dict],
    system_prompt: str,
    schema: dict,
    cache_path: Path,
    refresh: bool = False,
) -> list[dict]:
    """Make one LLM call per chunk, aggregate parsed annotations into one flat list.

    Cache file holds a list of {chunk_id, raw_response} so individual chunks
    can be re-run by editing the file. The order matches `chunks`.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached: dict[str, dict] = {}
    if cache_path.exists() and not refresh:
        existing = json.loads(cache_path.read_text(encoding="utf-8"))
        cached = {entry["chunk_id"]: entry["raw_response"] for entry in existing}
        print(f"[llm_call] {len(cached)} cached chunk responses at {cache_path}")

    new_cache: list[dict] = []
    all_annotations: list[dict] = []
    n = len(chunks)
    # Checkpoint to disk every CHECKPOINT_EVERY chunks so a mid-run failure
    # doesn't waste already-paid LLM calls. The cache file format stays the
    # same (list of {chunk_id, raw_response}) so resume on next invocation
    # picks up where this left off.
    CHECKPOINT_EVERY = 10
    new_calls_since_checkpoint = 0

    def _flush():
        cache_path.write_text(
            json.dumps(new_cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    for i, chunk in enumerate(chunks):
        cid = chunk["chunk_id"]
        if cid in cached:
            raw = cached[cid]
        else:
            print(f"[llm_call] chunk {i+1}/{n} ({cid}) — calling {MODEL}", flush=True)
            raw = _call_api(system_prompt, chunk["text"], schema)
            new_calls_since_checkpoint += 1
        new_cache.append({"chunk_id": cid, "raw_response": raw})

        try:
            payload = _parse_response(raw)
            all_annotations.extend(payload.get("annotations", []))
        except (LLMTruncated, LLMRefused, RuntimeError) as e:
            print(f"[llm_call] chunk {cid} produced no usable annotations: {e}")

        if new_calls_since_checkpoint >= CHECKPOINT_EVERY:
            _flush()
            print(f"[llm_call] checkpointed after {i+1}/{n}", flush=True)
            new_calls_since_checkpoint = 0

    _flush()
    print(f"[llm_call] cached {len(new_cache)} chunk responses, aggregated {len(all_annotations)} annotations")
    return all_annotations
