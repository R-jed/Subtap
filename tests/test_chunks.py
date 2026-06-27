"""Tests for VAD chunk splitting."""

from __future__ import annotations

import json
from pathlib import Path

from subtap.core.media import prepare_media
from subtap.core.vad import split_chunks
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk


def test_split_chunks_produces_jsonl(
    sample_wav: Path, test_config: SubtapConfig, tmp_path: Path
):
    """split_chunks should create chunks.jsonl with valid entries."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    prepare_media(sample_wav, ws, test_config)

    chunks = split_chunks(ws, test_config)

    assert len(chunks) >= 1
    assert ws.chunks_jsonl.exists()

    # Parse JSONL
    lines = ws.chunks_jsonl.read_text().strip().split("\n")
    assert len(lines) == len(chunks)
    for line in lines:
        data = json.loads(line)
        Chunk.model_validate(data)  # raises on invalid


def test_chunks_time_monotonic(
    sample_wav: Path, test_config: SubtapConfig, tmp_path: Path
):
    """Chunk time ranges should be monotonic and non-overlapping."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    prepare_media(sample_wav, ws, test_config)

    chunks = split_chunks(ws, test_config)

    for i, chunk in enumerate(chunks):
        assert chunk.chunk_id == i
        assert chunk.start_sec < chunk.end_sec
        if i > 0:
            assert chunk.start_sec >= chunks[i - 1].end_sec


def test_chunks_paths_exist(
    sample_wav: Path, test_config: SubtapConfig, tmp_path: Path
):
    """Each chunk's referenced WAV file should exist on disk."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    prepare_media(sample_wav, ws, test_config)

    chunks = split_chunks(ws, test_config)

    for chunk in chunks:
        chunk_file = ws.root / chunk.path
        assert chunk_file.exists(), f"Chunk file missing: {chunk_file}"
        assert chunk_file.stat().st_size > 0
