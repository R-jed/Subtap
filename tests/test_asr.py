"""Tests for ASR pipeline stage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest

from subtap.backends.asr.base import ASRBackend
from subtap.backends.asr import get_backend
from subtap.core.asr import load_chunks, run_asr
from subtap.core.media import prepare_media
from subtap.core.vad import split_chunks
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig, ASRConfig
from subtap.schemas.models import Chunk, ASRSegment


class MockASRBackend:
    """Mock ASR backend that returns deterministic output."""

    name = "mock-asr"

    def transcribe(
        self,
        chunks: list[Chunk],
        language: Optional[str] = None,
        hotwords: Optional[list[str]] = None,
    ) -> list[ASRSegment]:
        segments = []
        for chunk in chunks:
            segments.append(
                ASRSegment(
                    chunk_id=chunk.chunk_id,
                    segment_id=0,
                    start_sec=chunk.start_sec,
                    end_sec=chunk.end_sec,
                    text=f"mock transcription {chunk.chunk_id}",
                    confidence=0.95,
                )
            )
        return segments


def test_asr_backend_protocol():
    """MockASRBackend satisfies the ASRBackend protocol."""
    mock = MockASRBackend()
    assert isinstance(mock, ASRBackend)


def test_get_backend_mock_fails():
    """get_backend raises ValueError for unknown backend name."""
    config = ASRConfig(backend="nonexistent")
    try:
        get_backend(config)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)


def test_chunks_to_asr_jsonl(
    sample_wav: Path, test_config: SubtapConfig, tmp_path: Path
):
    """Full pipeline: prepare → chunk → mock ASR → asr.jsonl."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")

    # Prepare + chunk
    prepare_media(sample_wav, ws, test_config)
    chunks = split_chunks(ws, test_config)
    assert len(chunks) >= 1

    # Run ASR with mock backend
    test_config.asr.backend = "mock-asr"
    # Patch the get_backend reference that asr.py imported
    import subtap.core.asr as asr_module

    original = asr_module.get_backend
    asr_module.get_backend = lambda *_a, **_k: MockASRBackend()
    try:
        result = run_asr(ws, test_config)
    finally:
        asr_module.get_backend = original

    assert result["segment_count"] == len(chunks)
    assert ws.asr_jsonl.exists()

    # Validate JSONL content
    lines = ws.asr_jsonl.read_text().strip().split("\n")
    assert len(lines) == len(chunks)
    for line in lines:
        data = json.loads(line)
        seg = ASRSegment.model_validate(data)
        assert seg.text.startswith("mock transcription")
        assert seg.chunk_id >= 0


def test_asr_chunk_id_alignment(
    sample_wav: Path, test_config: SubtapConfig, tmp_path: Path
):
    """ASR segment chunk_ids must align with chunk chunk_ids."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    prepare_media(sample_wav, ws, test_config)
    split_chunks(ws, test_config)

    test_config.asr.backend = "mock-asr"
    import subtap.core.asr as asr_module

    original = asr_module.get_backend
    asr_module.get_backend = lambda *_a, **_k: MockASRBackend()
    try:
        run_asr(ws, test_config)
    finally:
        asr_module.get_backend = original

    # Load both and verify alignment
    chunksLoaded = load_chunks(ws.chunks_jsonl)
    lines = ws.asr_jsonl.read_text().strip().split("\n")
    segments = [ASRSegment.model_validate_json(line) for line in lines]

    chunk_ids = {c.chunk_id for c in chunksLoaded}
    seg_ids = {s.chunk_id for s in segments}
    assert chunk_ids == seg_ids


def test_run_asr_uses_selected_glossary(
    sample_wav: Path,
    test_config: SubtapConfig,
    tmp_path: Path,
    monkeypatch,
):
    import subtap.core.asr as asr_module

    selected = tmp_path / "selected.yaml"
    selected.write_text("理光GR4=李光机亚四\n", encoding="utf-8")
    default = tmp_path / ".subtap" / "glossaries" / "default.yaml"
    default.parent.mkdir(parents=True)
    default.write_text("默认词=错误词\n", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    captured_hotwords = []

    class CapturingBackend(MockASRBackend):
        def transcribe(self, chunks, language=None, hotwords=None):
            captured_hotwords.extend(hotwords or [])
            return super().transcribe(chunks, language=language, hotwords=hotwords)

    ws = Workspace(test_config, base_dir=tmp_path / "work")
    prepare_media(sample_wav, ws, test_config)
    split_chunks(ws, test_config)
    test_config.clean.glossary_path = str(selected)
    monkeypatch.setattr(asr_module, "get_backend", lambda *_a, **_k: CapturingBackend())

    run_asr(ws, test_config)

    assert "理光GR4" in captured_hotwords
    assert "默认词" not in captured_hotwords


def test_selected_missing_glossary_fails(tmp_path):
    from subtap.core.asr import _load_hotwords_from_glossary

    with pytest.raises(FileNotFoundError, match="热词表不存在"):
        _load_hotwords_from_glossary(glossary_path=str(tmp_path / "missing.yaml"))


def test_http_asr_empty_chunks_returns_empty():
    """HttpASRBackend returns empty result for empty chunks."""
    from subtap.backends.asr.http_asr import HttpASRBackend

    config = ASRConfig(backend="http-asr")
    backend = HttpASRBackend(config)
    assert backend.transcribe([]) == []


def test_cli_transcribe_runnable(
    sample_wav: Path, test_config: SubtapConfig, tmp_path: Path, monkeypatch
):
    """CLI transcribe command runs without crash (mock backend)."""
    from typer.testing import CliRunner
    from subtap.cli import app

    # Setup workspace with chunks
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    prepare_media(sample_wav, ws, test_config)
    split_chunks(ws, test_config)

    # Patch get_backend to return mock (asr.py holds a local ref)
    import subtap.core.asr as asr_module

    monkeypatch.setattr(asr_module, "get_backend", lambda *_a, **_k: MockASRBackend())

    # Patch load_config (imported locally inside CLI functions)
    import subtap.schemas.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "load_config", lambda p: test_config)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "fakehome")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "transcribe",
            str(ws.source_audio),
            "-w",
            str(ws.root),
        ],
    )
    assert result.exit_code == 0
    assert "完成" in result.output
