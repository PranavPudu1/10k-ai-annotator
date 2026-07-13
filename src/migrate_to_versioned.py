"""Migrate pre-versioning per-doc output into the versioned layout.

Before:
    output/{slug}/aligned.json
    output/{slug}/ai_annotations.json
    output/{slug}/llm_raw_response.json

After:
    output/{slug}/versions/baseline/aligned.json
    output/{slug}/versions/baseline/ai_annotations.json
    output/{slug}/versions/baseline/llm_raw_response.json
    output/{slug}/versions/baseline/meta.json

Idempotent: skips docs that already have versions/baseline/aligned.json.
Run: `python -m src.migrate_to_versioned [--dry-run]`
"""
from __future__ import annotations
import argparse
import datetime as dt
import json

from .config import OUTPUT_DIR, versioned_paths_for
from .strategies import BASELINE_STRATEGY


_FILES_TO_MOVE = ("aligned.json", "ai_annotations.json", "llm_raw_response.json")


def migrate(dry_run: bool = False) -> tuple[int, int]:
    if not OUTPUT_DIR.exists():
        print("output/ does not exist — nothing to migrate")
        return 0, 0

    moved, skipped = 0, 0
    for slug_dir in sorted(OUTPUT_DIR.iterdir()):
        if not slug_dir.is_dir():
            continue
        # Heuristic: a doc dir contains a slug-shaped name like "apple_2024".
        # Skip clearly non-doc directories (e.g. nothing named like a slug).
        if "_" not in slug_dir.name:
            continue
        slug = slug_dir.name
        v_paths = versioned_paths_for(slug, BASELINE_STRATEGY.id)

        if v_paths["aligned_path"].exists():
            print(f"  skip {slug} (already versioned)")
            skipped += 1
            continue

        legacy_aligned = slug_dir / "aligned.json"
        if not legacy_aligned.exists():
            print(f"  skip {slug} (no legacy aligned.json)")
            skipped += 1
            continue

        print(f"  migrate {slug}")
        if dry_run:
            moved += 1
            continue

        v_paths["version_dir"].mkdir(parents=True, exist_ok=True)
        for filename in _FILES_TO_MOVE:
            src = slug_dir / filename
            if not src.exists():
                continue
            dst = v_paths["version_dir"] / filename
            src.rename(dst)
        meta = {
            "id": BASELINE_STRATEGY.id,
            "name": BASELINE_STRATEGY.name,
            "description": BASELINE_STRATEGY.description,
            "chunker": BASELINE_STRATEGY.chunker,
            "chunker_params": BASELINE_STRATEGY.chunker_params,
            "model": BASELINE_STRATEGY.model,
            "migrated_from_legacy_layout": True,
            "migrated_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        v_paths["meta_path"].write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        moved += 1

    return moved, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    moved, skipped = migrate(dry_run=args.dry_run)
    print(f"\nDone. moved={moved} skipped={skipped} (dry_run={args.dry_run})")


if __name__ == "__main__":
    main()
