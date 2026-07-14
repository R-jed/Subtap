"""Phase 22: Qwen3 MLX ASR runtime contract."""

from __future__ import annotations

from subtap.core.asr import run_asr
from subtap.core.workspace import Workspace
from subtap.schemas.asr import ASRDraft
from subtap.schemas.config import ASRConfig, SubtapConfig
from subtap.schemas.models import ASRSegment, Chunk


class MockASRBackend:
    name = "mlx-qwen-asr"

    def __init__(self):
        self._model = object()

    def transcribe(self, chunks, language=None, hotwords=None):
        return [
            ASRSegment(
                chunk_id=chunk.chunk_id,
                segment_id=0,
                start_sec=chunk.start_sec,
                end_sec=chunk.end_sec,
                text="测试字幕",
                confidence=0.9,
            )
            for chunk in chunks
        ]

    def release_model(self):
        self._model = None


def test_asr_config_supports_model_quantization_and_no_keep_alive():
    """ASR config should express model, quantization, and non-resident defaults."""
    config = ASRConfig()
    assert config.model == "asr_0.6b"
    assert config.quantization == "q8"
    assert config.keep_model_alive is False


def test_run_asr_writes_asr_draft_contract(monkeypatch, tmp_path):
    """run_asr should write ASRDraft reference-timing artifact."""
    config = SubtapConfig()
    config.asr.model = "asr_0.6b"
    config.asr.quantization = "q8"
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()

    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=1.0, path="chunks/chunk.wav")
    workspace.chunks_jsonl.write_text(chunk.model_dump_json() + "\n", encoding="utf-8")
    (workspace.root / "chunks").mkdir(exist_ok=True)
    (workspace.root / "chunks" / "chunk.wav").write_bytes(b"fake")

    backend = MockASRBackend()
    monkeypatch.setattr("subtap.core.asr.get_backend", lambda *_a, **_k: backend)

    result = run_asr(workspace, config)

    assert result["segment_count"] == 1
    assert workspace.asr_draft_jsonl.exists()
    draft = ASRDraft.model_validate_json(
        workspace.asr_draft_jsonl.read_text(encoding="utf-8").strip()
    )
    assert draft.provider == "qwen3_mlx"
    assert draft.model == "asr_0.6b-q8"
    assert draft.is_reference_only() is True
    assert backend._model is None
