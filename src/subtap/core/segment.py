"""Segment pipeline stage: cleaned.jsonl → sentences.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from subtap.core.segmentation import segment_clean_segments
from subtap.schemas.models import CleanSegment, SentenceSegment
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


def write_sentences(sentences: list[SentenceSegment], output_path: Path) -> None:
    """Write SentenceSegments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in sentences:
            f.write(seg.model_dump_json() + "\n")


def run_segment(workspace: Workspace, chunk_start: float = 0.0, chunk_end: float = 1.0) -> dict:
    """Run segment stage: load cleaned → split → sentences.jsonl.

    Args:
        workspace: Workspace instance with paths.
        chunk_start: Start time of the source chunk.
        chunk_end: End time of the source chunk.

    Returns:
        Dict with sentence_count.
    """
    segments = load_clean_segments(workspace.cleaned_jsonl)
    if not segments:
        raise ValueError(f"No clean segments found in {workspace.cleaned_jsonl}")

    sentences = segment_clean_segments(segments, chunk_start, chunk_end)
    write_sentences(sentences, workspace.sentences_jsonl)

    return {"sentence_count": len(sentences)}
