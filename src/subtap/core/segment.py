"""Segment pipeline stage: cleaned.jsonl → sentences.jsonl."""

from __future__ import annotations

from pathlib import Path

from subtap.core.segmentation import segment_clean_segments
from subtap.schemas.models import CleanSegment, SentenceSegment, Chunk
from subtap.core.workspace import Workspace


def load_clean_segments(cleaned_jsonl: Path) -> list[CleanSegment]:
    """Load CleanSegments from JSONL."""
    segments: list[CleanSegment] = []
    with open(cleaned_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(CleanSegment.model_validate_json(line))
    return segments


def load_chunk_boundaries(chunks_jsonl: Path) -> tuple[float, float]:
    """Load chunk boundaries from chunks.jsonl.

    Returns:
        Tuple of (start_sec, end_sec) from the first chunk.
    """
    with open(chunks_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                chunk = Chunk.model_validate_json(line)
                return chunk.start_sec, chunk.end_sec
    raise ValueError(f"No chunks found in {chunks_jsonl}")


def write_sentences(sentences: list[SentenceSegment], output_path: Path) -> None:
    """Write SentenceSegments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in sentences:
            f.write(seg.model_dump_json() + "\n")


def run_segment(
    workspace: Workspace,
    chunk_start: float | None = None,
    chunk_end: float | None = None,
    language: str = "zh",
) -> dict:
    """Run segment stage: load cleaned → split → sentences.jsonl.

    Args:
        workspace: Workspace instance with paths.
        chunk_start: Start time of the source chunk. If None, reads from chunks.jsonl.
        chunk_end: End time of the source chunk. If None, reads from chunks.jsonl.
        language: Language code ("zh" or "en").

    Returns:
        Dict with sentence_count.
    """
    # Read chunk boundaries from chunks.jsonl if not provided
    if chunk_start is None or chunk_end is None:
        chunk_start, chunk_end = load_chunk_boundaries(workspace.chunks_jsonl)

    segments = load_clean_segments(workspace.cleaned_jsonl)
    if not segments:
        raise ValueError(f"No clean segments found in {workspace.cleaned_jsonl}")

    sentences = segment_clean_segments(segments, chunk_start, chunk_end, language=language)
    write_sentences(sentences, workspace.sentences_jsonl)

    return {"sentence_count": len(sentences)}
