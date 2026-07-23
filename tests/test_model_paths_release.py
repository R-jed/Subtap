"""Release-safe model path wiring tests."""

from __future__ import annotations

from pathlib import Path

from subtap.core.align import run_align
from subtap.core.asr import run_asr
from subtap.core.workspace import Workspace
from subtap.schemas.config import ModelConfig, SubtapConfig
from subtap.schemas.models import ASRSegment, Chunk, SentenceSegment


class CapturingASRBackend:
    name = "mlx-qwen-asr"

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def transcribe(self, chunks, language=None, hotwords=None):
        return [
            ASRSegment(
                chunk_id=chunks[0].chunk_id,
                segment_id=0,
                start_sec=chunks[0].start_sec,
                end_sec=chunks[0].end_sec,
                text="测试字幕",
            )
        ]

    def release_model(self):
        pass


class CapturingAlignBackend:
    name = "mlx-qwen-aligner"

    def align(self, sentences, audio_path):
        return []

    def release_model(self):
        pass


def test_run_asr_passes_configured_model_root(monkeypatch, tmp_path: Path):
    config = SubtapConfig(models=ModelConfig(root=str(tmp_path / "custom-models")))
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=1.0, path="chunks/chunk.wav")
    workspace.chunks_jsonl.write_text(chunk.model_dump_json() + "\n", encoding="utf-8")
    (workspace.root / "chunks").mkdir(exist_ok=True)
    (workspace.root / "chunks" / "chunk.wav").write_bytes(b"fake")

    seen = {}

    def fake_get_backend(config_arg, remote_api=None, model_root=None):
        seen["model_root"] = model_root
        return CapturingASRBackend()

    monkeypatch.setattr("subtap.core.asr.get_backend", fake_get_backend)

    run_asr(workspace, config)

    assert seen["model_root"] == tmp_path / "custom-models"


def test_run_align_passes_configured_model_root(monkeypatch, tmp_path: Path):
    config = SubtapConfig(models=ModelConfig(root=str(tmp_path / "custom-models")))
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    sentence = SentenceSegment(
        sentence_id=0,
        chunk_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="测试字幕",
        source_text="测试字幕",
    )
    workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n", encoding="utf-8"
    )
    workspace.source_audio.write_bytes(b"fake")

    seen = {}

    def fake_get_aligner_backend(config_arg, model_root=None):
        seen["model_root"] = model_root
        return CapturingAlignBackend()

    monkeypatch.setattr(
        "subtap.core.align.get_aligner_backend", fake_get_aligner_backend
    )

    run_align(workspace, config)

    assert seen["model_root"] == tmp_path / "custom-models"
