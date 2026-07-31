"""Real batch local pipeline integration tests.

These tests invoke batch-transcribe through the real Typer command,
real batch processing loop, real Pipeline, real RichRunner stage loop,
real run_clean(), real segment, and real export.

Heavy media/model boundaries are stubbed at their function boundaries.
The align stub reads the actual sentences.jsonl produced by the real
segment stage — final subtitle is causally derived from real clean and
segment output.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from subtap.cli import app
from subtap.core.pipeline import Pipeline
from subtap.schemas.models import ASRSegment, Chunk

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _seed_asr_init(original_init, texts: list[str]):
    """Create an instrumented Pipeline.__init__ that seeds ASR data."""

    def instrumented(self, config, work_dir, **kwargs):
        original_init(self, config, work_dir, **kwargs)
        self.workspace.ensure_dirs()
        self.workspace.asr_dir.mkdir(parents=True, exist_ok=True)
        with open(self.workspace.asr_jsonl, "w") as f:
            for i, text in enumerate(texts):
                seg = ASRSegment(
                    chunk_id=0,
                    segment_id=i,
                    start_sec=float(i),
                    end_sec=float(i + 1),
                    text=text,
                )
                f.write(seg.model_dump_json() + "\n")

    return instrumented


def _stub_prepare(input_path, workspace, config):
    """Stub prepare_media: write media_info.json."""
    info = {"duration": 1.0, "sample_rate": 16000, "channels": 1}
    ws_root = Path(workspace.root)
    ws_root.mkdir(parents=True, exist_ok=True)
    (ws_root / "media_info.json").write_text(json.dumps(info))
    return SimpleNamespace(model_dump=lambda: info)


def _stub_chunks(workspace, config):
    """Stub split_chunks: return one chunk."""
    ws_root = Path(workspace.root)
    ws_root.mkdir(parents=True, exist_ok=True)
    chunk = Chunk(
        chunk_id=0,
        start_sec=0.0,
        end_sec=1.0,
        path=str(Path(workspace.root) / "chunk0.wav"),
    )
    with open(workspace.chunks_jsonl, "w") as f:
        f.write(chunk.model_dump_json() + "\n")
    return [chunk]


def _stub_asr(workspace, config, **kwargs):
    """Stub run_asr: data already seeded."""
    count = 0
    if workspace.asr_jsonl.exists():
        count = sum(1 for _ in open(workspace.asr_jsonl))
    return {"segment_count": count}


def _stub_align(workspace, config, **kwargs):
    """Stub run_align: read actual sentences.jsonl, write aligned.jsonl."""
    sentences_path = kwargs.get("sentences_path") or workspace.sentences_jsonl
    aligned = []
    with open(sentences_path) as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                aligned.append(
                    {
                        "sentence_id": rec.get("sentence_id", 0),
                        "start_sec": rec.get("start_sec", 0.0),
                        "end_sec": rec.get("end_sec", 1.0),
                        "text": rec["text"],
                    }
                )
    with open(workspace.aligned_jsonl, "w") as f:
        for rec in aligned:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"aligned_count": len(aligned)}


def _stub_hotword(workspace, **kwargs):
    """Stub run_hotword: no replacements."""
    return {"replaced": 0, "total": 0}


class TestBatchRealRunner:
    """Batch with real Pipeline and real RichRunner stage loop."""

    def test_batch_local_succeeds_with_real_runner(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Batch item with enhance=local: real runner drives full pipeline through export."""
        original_init = Pipeline.__init__
        instrumented = _seed_asr_init(original_init, ["batch  test  segment"])

        monkeypatch.setattr(Pipeline, "__init__", instrumented)
        monkeypatch.setattr("subtap.core.media.prepare_media", _stub_prepare)
        monkeypatch.setattr("subtap.core.vad.split_chunks", _stub_chunks)
        monkeypatch.setattr("subtap.core.asr.run_asr", _stub_asr)
        monkeypatch.setattr("subtap.core.align.run_align", _stub_align)
        monkeypatch.setattr("subtap.core.hotword.run_hotword", _stub_hotword)

        # Stub model validation
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )
        monkeypatch.setattr("subtap.core.models.apply_asr_mode", lambda _c, _m: None)
        monkeypatch.setattr("subtap.core.models.asr_mode_for_model", lambda _m: "fast")

        # Prevent LLM backend calls
        llm_calls = []

        def fail_if_llm(*_a, **_k):
            llm_calls.append(True)
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_llm)

        audio = tmp_path / "voice.wav"
        audio.write_bytes(b"audio")
        output = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "batch-transcribe",
                str(audio),
                "--enhance",
                "local",
                "--output-dir",
                str(output),
                "--no-confirm",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output

        # Verify manifest
        manifest = output / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        assert saved["total"] == 1
        assert saved["succeeded"] == 1
        assert saved["failed"] == 0
        assert saved["items"][0]["status"] == "succeeded"

        # Verify surviving artifacts (cleaned.jsonl and sentences.jsonl are
        # deleted by cleanroom.clean_intermediate_files() after successful batch)
        item_work = output / "voice_wav" / "work"
        assert (item_work / "aligned.jsonl").exists()

        # Verify final subtitle exists and is non-empty
        srt_path = output / "voice_wav" / "voice.srt"
        assert srt_path.exists()
        srt_text = srt_path.read_text()
        assert srt_text.strip()

        # Verify no LLM backend was called
        assert llm_calls == []

        # Verify no external disclosure text for local execution
        assert "发送" not in result.output

    def test_batch_default_local_clean_produces_artifact(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Default batch (no --enhance): real local clean produces artifacts."""
        original_init = Pipeline.__init__
        instrumented = _seed_asr_init(original_init, ["default  batch  test"])

        monkeypatch.setattr(Pipeline, "__init__", instrumented)
        monkeypatch.setattr("subtap.core.media.prepare_media", _stub_prepare)
        monkeypatch.setattr("subtap.core.vad.split_chunks", _stub_chunks)
        monkeypatch.setattr("subtap.core.asr.run_asr", _stub_asr)
        monkeypatch.setattr("subtap.core.align.run_align", _stub_align)
        monkeypatch.setattr("subtap.core.hotword.run_hotword", _stub_hotword)
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )
        monkeypatch.setattr("subtap.core.models.apply_asr_mode", lambda _c, _m: None)
        monkeypatch.setattr("subtap.core.models.asr_mode_for_model", lambda _m: "fast")

        llm_calls = []

        def fail_if_llm(*_a, **_k):
            llm_calls.append(True)
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_llm)

        audio = tmp_path / "voice.wav"
        audio.write_bytes(b"audio")
        output = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "batch-transcribe",
                str(audio),
                "--output-dir",
                str(output),
                "--no-confirm",
                "--json",
            ],
        )

        assert result.exit_code == 0, result.output

        # Verify manifest success
        manifest = output / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        assert saved["items"][0]["status"] == "succeeded"

        # Verify surviving artifacts
        item_work = output / "voice_wav" / "work"
        assert (item_work / "aligned.jsonl").exists()

        # Verify final subtitle
        srt_path = output / "voice_wav" / "voice.srt"
        assert srt_path.exists()
        assert srt_path.read_text().strip()

        assert llm_calls == []
