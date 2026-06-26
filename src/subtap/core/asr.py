"""ASR pipeline stage: load chunks → transcribe → write asr.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from subtap.backends.asr import get_backend
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk, ASRSegment
from subtap.core.workspace import Workspace


def load_chunks(chunks_jsonl: Path) -> list[Chunk]:
    """Load chunks from JSONL file."""
    chunks: list[Chunk] = []
    with open(chunks_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(Chunk.model_validate_json(line))
    return chunks


def write_asr_segments(segments: list[ASRSegment], output_path: Path) -> None:
    """Write ASR segments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in segments:
            f.write(seg.model_dump_json() + "\n")


def run_asr(
    workspace: Workspace,
    config: SubtapConfig,
    backend_name: str | None = None,
) -> dict:
    """Run ASR stage: load chunks, transcribe, write asr.jsonl.

    Args:
        workspace: Workspace instance with paths.
        config: Subtap config (used for ASR backend settings).
        backend_name: Override backend name (defaults to config).

    Returns:
        Dict with segment_count.
    """
    # Load chunks
    chunks = load_chunks(workspace.chunks_jsonl)
    if not chunks:
        raise ValueError(f"No chunks found in {workspace.chunks_jsonl}")

    # Resolve backend
    asr_config = config.asr.model_copy()
    if backend_name:
        asr_config.backend = backend_name

    backend = get_backend(asr_config)

    # Resolve chunk paths to absolute
    abs_chunks: list[Chunk] = []
    for chunk in chunks:
        chunk_path = Path(chunk.path)
        if not chunk_path.is_absolute():
            chunk_path = workspace.root / chunk_path
        abs_chunks.append(chunk.model_copy(update={"path": str(chunk_path)}))

    # Transcribe
    segments = backend.transcribe(
        abs_chunks,
        language=None,
        hotwords=config.asr.hotwords or None,
    )

    # Write asr.jsonl
    write_asr_segments(segments, workspace.asr_jsonl)

    return {"segment_count": len(segments)}
