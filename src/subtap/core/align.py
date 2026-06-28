"""Align pipeline stage: sentences.jsonl → forced alignment → aligned.jsonl."""

from __future__ import annotations

from pathlib import Path

from subtap.backends.align import get_aligner_backend
from subtap.schemas.alignment import AlignedSubtitle
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import SentenceSegment, AlignedSegment
from subtap.core.workspace import Workspace


def load_sentences(sentences_jsonl: Path) -> list[SentenceSegment]:
    """Load SentenceSegments from JSONL."""
    segments: list[SentenceSegment] = []
    with open(sentences_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(SentenceSegment.model_validate_json(line))
    return segments


def write_aligned(segments: list[AlignedSegment], output_path: Path) -> None:
    """Write AlignedSegments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in segments:
            f.write(seg.model_dump_json() + "\n")


def write_aligned_subtitles(segments: list[AlignedSegment], output_path: Path) -> None:
    """Write AlignedSubtitle final-timing artifact."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in segments:
            subtitle = AlignedSubtitle(
                subtitle_id=seg.sentence_id,
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
                text=seg.text,
            )
            f.write(subtitle.model_dump_json() + "\n")


def run_align(
    workspace: Workspace,
    config: SubtapConfig,
    backend_name: str | None = None,
) -> dict:
    """Run align stage: load sentences → forced alignment → aligned.jsonl.

    Args:
        workspace: Workspace instance with paths.
        config: Subtap config.
        backend_name: Override aligner backend name.

    Returns:
        Dict with aligned_count.
    """
    # Load sentences
    sentences = load_sentences(workspace.sentences_jsonl)
    if not sentences:
        raise ValueError(f"No sentences found in {workspace.sentences_jsonl}")

    # Resolve backend
    align_config = config.align.model_copy()
    if backend_name:
        align_config.backend = backend_name

    backend = get_aligner_backend(align_config)

    # Align
    try:
        aligned = backend.align(sentences, workspace.source_audio)
    finally:
        if not align_config.keep_model_alive and hasattr(backend, "release_model"):
            backend.release_model()

    # Write aligned.jsonl
    write_aligned(aligned, workspace.aligned_jsonl)
    write_aligned_subtitles(aligned, workspace.aligned_subtitles_jsonl)

    return {"aligned_count": len(aligned)}
