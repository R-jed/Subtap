"""Segment pipeline stage: cleaned.jsonl → sentences.jsonl."""

from __future__ import annotations

from pathlib import Path

from subtap.core.segmentation import segment_clean_segments
from subtap.schemas.models import RawCleanSegment, SentenceSegment, Chunk
from subtap.core.workspace import Workspace


def load_clean_segments(cleaned_jsonl: Path) -> list[RawCleanSegment]:
    """Load RawCleanSegments from JSONL."""
    segments: list[RawCleanSegment] = []
    with open(cleaned_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(RawCleanSegment.model_validate_json(line))
    return segments


def load_chunk_boundaries(chunks_jsonl: Path) -> dict[int, tuple[float, float]]:
    """Load chunk boundaries from chunks.jsonl.

    Returns:
        Dict mapping chunk_id to (start_sec, end_sec).
    """
    boundaries: dict[int, tuple[float, float]] = {}
    with open(chunks_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                chunk = Chunk.model_validate_json(line)
                boundaries[chunk.chunk_id] = (chunk.start_sec, chunk.end_sec)
    if not boundaries:
        raise ValueError(f"No chunks found in {chunks_jsonl}")
    return boundaries


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
    segments = load_clean_segments(workspace.cleaned_jsonl)
    if not segments:
        raise ValueError(f"No clean segments found in {workspace.cleaned_jsonl}")

    # If chunk boundaries not provided, load from chunks.jsonl and group by chunk
    if chunk_start is None or chunk_end is None:
        chunk_boundaries = load_chunk_boundaries(workspace.chunks_jsonl)

        # Group segments by source_chunk_id
        from collections import defaultdict

        segments_by_chunk: dict[int, list[RawCleanSegment]] = defaultdict(list)
        for seg in segments:
            segments_by_chunk[seg.source_chunk_id].append(seg)

        # Process each chunk group
        all_sentences: list[SentenceSegment] = []
        for chunk_id, chunk_segs in sorted(segments_by_chunk.items()):
            if chunk_id not in chunk_boundaries:
                raise ValueError(f"Chunk {chunk_id} not found in chunks.jsonl")
            c_start, c_end = chunk_boundaries[chunk_id]
            chunk_sentences = segment_clean_segments(
                chunk_segs, c_start, c_end, language=language
            )
            all_sentences.extend(chunk_sentences)

        # Re-assign globally unique sentence_ids
        for i, sent in enumerate(all_sentences):
            sent.sentence_id = i

        write_sentences(all_sentences, workspace.sentences_jsonl)
        return {"sentence_count": len(all_sentences)}
    else:
        # Use provided boundaries (for backward compatibility)
        sentences = segment_clean_segments(
            segments, chunk_start, chunk_end, language=language
        )
        write_sentences(sentences, workspace.sentences_jsonl)
        return {"sentence_count": len(sentences)}
