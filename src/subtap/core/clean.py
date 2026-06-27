"""Clean pipeline stage: ASR segments → replacement → LLM → cleaned.jsonl."""

from __future__ import annotations

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


def run_clean(
    workspace: Workspace,
    config: SubtapConfig,
    llm_backend_name: str | None = None,
    glossary_path: str | None = None,
    style_rules: list[str] | None = None,
) -> dict:
    """Run clean stage: load ASR → replacement → LLM → cleaned.jsonl.

    Steps:
    1. Load ASR segments from workspace.asr_jsonl
    2. Apply deterministic glossary replacements
    3. Pass through LLM backend for ASR error correction
    4. Write cleaned.jsonl to workspace

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

    # Step 2: LLM cleaning (if backend available)
    clean_config = config.clean.model_copy()
    if llm_backend_name:
        clean_config.backend = llm_backend_name

    try:
        llm = get_llm_backend(clean_config)
        if llm is not None:
            cleaned = llm.clean_segments(
                replaced,
                glossary=glossary,
                style_rules=style_rules or config.clean.style_rules,
            )
        else:
            cleaned = replaced
    except ValueError:
        # Unknown backend — skip LLM, use replaced-only
        cleaned = replaced

    # Write cleaned.jsonl
    write_clean_segments(cleaned, workspace.cleaned_jsonl)

    return {"segment_count": len(cleaned)}
