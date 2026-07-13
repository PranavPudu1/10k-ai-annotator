"""Paths, model id, and env loading.

Multi-doc layout: input filings at `data/10ks/{slug}.htm`, outputs at
`output/{slug}/...`. Call `paths_for(slug)` to get all per-doc paths.
"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = DATA_DIR / "10ks"
OUTPUT_DIR = ROOT / "output"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
HUMAN_CSV_PATH = DATA_DIR / "humanannotations.csv"

MODEL = "gpt-5.4-mini"
MAX_OUTPUT_TOKENS = 32000
TIMEOUT_SECONDS = 600


def paths_for(slug: str) -> dict[str, Path]:
    """Per-doc paths that are SHARED across strategies (text, sentences, keyword hits).

    For version-specific paths (aligned.json etc.) call versioned_paths_for.
    """
    out_dir = OUTPUT_DIR / slug
    return {
        "out_dir": out_dir,
        "html_path": DOCS_DIR / f"{slug}.htm",
        "txt_path": out_dir / "text.txt",
        "sentences_path": out_dir / "sentences.json",
        "keyword_hits_path": out_dir / "keyword_hits.json",
        # Default (non-versioned) paths still returned so legacy callers keep working
        # until everything migrates to versioned_paths_for.
        "llm_raw_path": out_dir / "llm_raw_response.json",
        "ai_annotations_path": out_dir / "ai_annotations.json",
        "aligned_path": out_dir / "aligned.json",
    }


def versioned_paths_for(slug: str, version_id: str) -> dict[str, Path]:
    """Paths for a specific (doc, strategy version)."""
    out_dir = OUTPUT_DIR / slug
    version_dir = out_dir / "versions" / version_id
    return {
        "version_dir": version_dir,
        "meta_path": version_dir / "meta.json",
        "llm_raw_path": version_dir / "llm_raw_response.json",
        "ai_annotations_path": version_dir / "ai_annotations.json",
        "aligned_path": version_dir / "aligned.json",
    }


def ensure_doc_output_dir(slug: str) -> Path:
    out_dir = OUTPUT_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def load_env() -> None:
    """Load .env.local. Accept either OPENAI_API_KEY or `openai` as the key name."""
    load_dotenv(ROOT / ".env.local")
    if not os.environ.get("OPENAI_API_KEY"):
        raw = os.environ.get("openai", "")
        if raw:
            os.environ["OPENAI_API_KEY"] = raw.strip().strip('"').strip("'")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "No OpenAI API key found. Set OPENAI_API_KEY or `openai=` in .env.local"
        )
