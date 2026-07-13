"""End-to-end pipeline for one or many 10-Ks under a chosen strategy.

Per (doc, strategy): HTML -> sentences (shared) -> keyword hits (cached) ->
chunks per strategy -> LLM (per chunk if needed) -> dedupe -> align ->
write to `output/{slug}/versions/{strategy_id}/`.

CLI:
    python -m src.pipeline --doc apple_2024 --version baseline
    python -m src.pipeline --doc alphabet_2024 --version keyword_window_20
    python -m src.pipeline --missing --version keyword_window_20
    python -m src.pipeline --all --version baseline
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
import traceback
from pathlib import Path

from .align import align, write_aligned
from .chunkers import chunk_for_strategy
from .config import (
    ensure_doc_output_dir,
    load_env,
    paths_for,
    versioned_paths_for,
)
from .hai_feedback import format_examples_block, load_hai_csvs, select_few_shot_examples
from .html_extract import extract_html
from .keyword_filter import get_or_compute_hits, load_keywords
from .llm_call import call_model, call_model_per_chunk
from .multi_human_csv import load_human_for_doc
from .normalize import dedupe_annotations, validate_annotations
from .prompt_build import build_hai_tuned_prompt, build_json_schema, build_system_prompt
from .registry import discover_docs, get_doc
from .sentence_index import build_index, write_index
from .sequential_passage_workflow import run_sequential_passage_aware
from .sequential_workflow import run_sequential_batched
from .strategies import STRATEGIES, Strategy, get_strategy
from .taxonomy import load_taxonomy


def _write_meta(meta_path: Path, strategy: Strategy, n_chunks: int) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": strategy.id,
        "name": strategy.name,
        "display_label": strategy.label(),
        "description": strategy.description,
        "workflow": strategy.workflow,
        "prompt_builder": strategy.prompt_builder,
        "chunker": strategy.chunker,
        "chunker_params": strategy.chunker_params,
        "model": strategy.model,
        "n_chunks": n_chunks,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_prompt(strategy: Strategy, taxonomy: dict) -> str:
    from .config import DATA_DIR
    if strategy.prompt_builder == "hai_tuned":
        records = load_hai_csvs()
        examples = select_few_shot_examples(records)
        return build_hai_tuned_prompt(taxonomy, examples_block=format_examples_block(examples))
    if strategy.prompt_builder == "hai_tuned_v2":
        # v2 = principles-only. No few-shot block (avoiding overfit to specific examples).
        return build_hai_tuned_prompt(
            taxonomy,
            rules_path=DATA_DIR / "hai_dont_rules_v2.md",
            examples_block="",
        )
    return build_system_prompt(taxonomy)


def run_for(
    slug: str,
    strategy: Strategy,
    taxonomy: dict,
    refresh: bool = False,
    skip_llm: bool = False,
) -> dict:
    """Run the pipeline for a single (doc, strategy)."""
    doc = get_doc(slug)
    if doc is None:
        raise SystemExit(f"slug {slug!r} not in registry")
    if not doc.has_html:
        raise SystemExit(f"{slug}: HTML not found at {doc.html_path}")

    shared = doc.paths
    versioned = versioned_paths_for(slug, strategy.id)
    ensure_doc_output_dir(slug)
    versioned["version_dir"].mkdir(parents=True, exist_ok=True)

    print(f"\n=== {slug} :: {strategy.id} ===")
    print("[1/-] extracting HTML text")
    text = extract_html(doc.html_path, shared["txt_path"])
    print(f"      {len(text):,} chars, {len(text.split()):,} words")

    print("[2/-] building sentence index")
    if shared["sentences_path"].exists() and not refresh:
        sentences = json.loads(shared["sentences_path"].read_text(encoding="utf-8"))
        print(f"      using cached sentences ({len(sentences):,})")
    else:
        sentences = build_index(text)
        write_index(sentences, shared["sentences_path"])
        print(f"      {len(sentences):,} sentences")

    if strategy.workflow == "sequential":
        print("[3/4] sequential 4-phase workflow")
        if skip_llm and not versioned["llm_raw_path"].exists():
            raise SystemExit(f"{slug}: no cached LLM response; remove --skip-llm to make the call.")
        raw_items = run_sequential_batched(
            sentences, taxonomy,
            cache_path=versioned["llm_raw_path"], refresh=refresh,
        )
        n_chunks = 4
    elif strategy.workflow == "sequential_passage_aware":
        print("[3/4] V5 passage-aware sequential workflow (6 phases)")
        if skip_llm and not versioned["llm_raw_path"].exists():
            raise SystemExit(f"{slug}: no cached LLM response; remove --skip-llm to make the call.")
        raw_items = run_sequential_passage_aware(
            sentences, taxonomy,
            cache_path=versioned["llm_raw_path"], refresh=refresh,
        )
        n_chunks = 6
    else:
        print("[3/5] keyword hits (shared cache)")
        if strategy.chunker == "full_doc":
            hits = []
            print(f"      skipped — {strategy.chunker} chunker doesn't need hits")
        else:
            keywords = load_keywords()
            hits = get_or_compute_hits(slug, sentences, keywords)
            print(f"      {len(hits):,} sentences contain >=1 AI keyword (of {len(keywords)} terms)")

        print(f"[4/5] chunking via {strategy.chunker!r}")
        chunks = chunk_for_strategy(strategy.chunker, sentences, hits, strategy.chunker_params)
        if not chunks:
            raise SystemExit(f"{slug} :: {strategy.id}: no chunks produced (nothing to send to LLM)")
        total_sent = sum(len(c["sentence_indices"]) for c in chunks)
        print(f"      {len(chunks)} chunk(s) covering {total_sent} sentence-positions")

        print("[5/5] building prompt + schema + LLM call(s)")
        system_prompt = _build_prompt(strategy, taxonomy)
        schema = build_json_schema(taxonomy)

        if skip_llm and not versioned["llm_raw_path"].exists():
            raise SystemExit(f"{slug}: no cached LLM response; remove --skip-llm to make the call.")

        if len(chunks) == 1:
            payload = call_model(
                system_prompt, chunks[0]["text"], schema,
                cache_path=versioned["llm_raw_path"], refresh=refresh,
            )
            raw_items = payload.get("annotations", [])
        else:
            raw_items = call_model_per_chunk(
                chunks, system_prompt, schema,
                cache_path=versioned["llm_raw_path"], refresh=refresh,
            )
        n_chunks = len(chunks)

    deduped = dedupe_annotations(raw_items)
    valid_items, val_counts = validate_annotations(deduped, taxonomy)
    versioned["ai_annotations_path"].write_text(
        json.dumps(valid_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"      raw {len(raw_items)} -> deduped {len(deduped)} -> "
        f"kept {len(valid_items)}; validation counts={val_counts}"
    )

    print("[final] aligning AI + human against sentences")
    human_df = load_human_for_doc(slug)
    aligned = align(sentences, valid_items, human_df, taxonomy)
    write_aligned(aligned, versioned["aligned_path"])
    print(f"      counts: {aligned['counts']}")

    _write_meta(versioned["meta_path"], strategy, n_chunks=n_chunks)
    return aligned["counts"]


def _confirm(prompt: str) -> bool:
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI annotation pipeline for one or more 10-Ks under a chosen strategy.")
    parser.add_argument("--doc", action="append", default=[], help="Slug to run; repeatable.")
    parser.add_argument("--all", action="store_true", help="Run every doc with an HTML present.")
    parser.add_argument("--missing", action="store_true", help="Only run docs with HTML but no aligned.json for the selected version.")
    parser.add_argument("--version", default="baseline",
                        help=f"Strategy id. Known: {','.join(STRATEGIES)}. Default: baseline.")
    parser.add_argument("--refresh", action="store_true", help="Force fresh LLM calls (re-bill).")
    parser.add_argument("--skip-llm", action="store_true", help="Use cached LLM responses only; fail if missing.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts.")
    args = parser.parse_args()

    if not (args.doc or args.all or args.missing):
        parser.error("specify --doc SLUG, --missing, or --all")

    strategy = get_strategy(args.version)
    load_env()
    taxonomy = load_taxonomy()

    if args.all or args.missing:
        all_docs = discover_docs()
        runnable = [d for d in all_docs if d.has_html]
        if args.missing:
            runnable = [d for d in runnable if strategy.id not in d.versions]
        slugs = [d.slug for d in runnable]
    else:
        slugs = list(args.doc)

    if not slugs:
        print("Nothing to run.")
        return

    if (args.all or args.missing) and not args.yes:
        print(f"About to run {strategy.id!r} on {len(slugs)} doc(s):")
        for s in slugs:
            print(f"  - {s}")
        if not args.skip_llm:
            print("This makes one or more LLM call(s) per doc — real OpenAI bill incurred.")
        if not _confirm("Proceed? [y/N]: "):
            print("Aborted.")
            return

    ran, skipped, failed = [], [], []
    for slug in slugs:
        try:
            run_for(slug, strategy, taxonomy, refresh=args.refresh, skip_llm=args.skip_llm)
            ran.append(slug)
        except SystemExit as e:
            print(f"  ! {slug}: {e}")
            skipped.append(slug)
        except Exception as e:
            print(f"  ! {slug}: {type(e).__name__}: {e}")
            traceback.print_exc(file=sys.stderr)
            failed.append(slug)

    print(f"\nDone. ran={len(ran)} skipped={len(skipped)} failed={len(failed)}")
    if failed:
        print("Failed slugs:", ", ".join(failed))
    print("\n  streamlit run src/app.py")


if __name__ == "__main__":
    main()
