"""Clean pipeline stage: ASR segments → replacement → LLM → cleaned.jsonl."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from subtap.backends.llm import get_llm_backend
from subtap.core.replacement import apply_replacements
from subtap.schemas.config import SubtapConfig
from subtap.schemas.glossary import load_glossary
from subtap.schemas.models import ASRSegment, CleanSegment
from subtap.core.workspace import Workspace


def load_asr_segments(asr_jsonl: Path) -> list[ASRSegment]:
    """Load ASR segments from JSONL."""
    segments: list[ASRSegment] = []
    with open(asr_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(ASRSegment.model_validate_json(line))
    return segments


def write_clean_segments(segments: list[CleanSegment], output_path: Path) -> None:
    """Write clean segments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in segments:
            f.write(seg.model_dump_json() + "\n")


def local_clean_text(text: str, glossary: dict | None = None) -> str:
    """Local rule-based text cleaning. No LLM dependency.

    Steps:
    1. Normalize unicode (NFKC)
    2. Normalize full-width digits to half-width
    3. Remove extra whitespace
    4. Apply glossary replacements
    """
    # 1. Unicode normalization
    text = unicodedata.normalize("NFKC", text)

    # 2. Full-width digit normalization (１２３ → 123)
    text = re.sub(r"[０-９]", lambda m: chr(ord(m.group()) - 0xFEE0), text)

    # 3. Remove extra spaces
    text = re.sub(r"\s+", " ", text).strip()

    # 4. Glossary replacement
    if glossary:
        for wrong, correct in glossary.items():
            text = text.replace(wrong, correct)

    return text


def run_clean(
    workspace: Workspace,
    config: SubtapConfig,
    llm_backend_name: str | None = None,
    glossary_path: str | None = None,
    style_rules: list[str] | None = None,
) -> dict:
    """Run clean stage: load ASR → local clean → replacement → LLM → cleaned.jsonl.

    Steps:
    1. Load ASR segments from workspace.asr_jsonl
    2. Apply local rule-based cleaning (unicode, full-width digits, whitespace)
    3. Apply deterministic glossary replacements
    4. Pass through LLM backend for ASR error correction (optional)
    5. Write cleaned.jsonl to workspace

    Args:
        workspace: Workspace instance with paths.
        config: Subtap config.
        llm_backend_name: Override LLM backend (e.g. "ollama:qwen3-coder").
        glossary_path: Path to glossary YAML file.
        style_rules: Additional style rules for LLM.

    Returns:
        Dict with segment_count.
    """
    # Load ASR segments
    segments = load_asr_segments(workspace.asr_jsonl)
    if not segments:
        raise ValueError(f"No ASR segments found in {workspace.asr_jsonl}")

    # Load glossary
    glossary_file = glossary_path or config.clean.glossary_path
    glossary = load_glossary(Path(glossary_file) if glossary_file else None)

    # Step 1: Deterministic replacement (no LLM)
    replaced = apply_replacements(segments, glossary)

    # Step 2: Local cleaning (always runs, no LLM dependency)
    for seg in replaced:
        seg.cleaned_text = local_clean_text(seg.cleaned_text)

    # Step 3: LLM cleaning (optional, never blocks)
    clean_config = config.clean.model_copy()
    if llm_backend_name:
        clean_config.backend = llm_backend_name

    try:
        if clean_config.backend.startswith("openai:"):
            llm = get_llm_backend(clean_config, config.remote_api)
        else:
            llm = get_llm_backend(clean_config)
        if llm is not None:
            cleaned = llm.clean_segments(
                replaced,
                glossary=glossary,
                style_rules=style_rules or config.clean.style_rules,
            )
        else:
            cleaned = replaced
    except (ValueError, Exception):
        # LLM failed, use local-cleaned result
        cleaned = replaced

    # Write cleaned.jsonl
    write_clean_segments(cleaned, workspace.cleaned_jsonl)

    return {"segment_count": len(cleaned)}
