"""Tests for productized batch transcription manifest."""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def _make_mock_config():
    """Create a mock config with all required attributes."""
    config = SimpleNamespace()
    config.output = SimpleNamespace()
    config.output.timestamp = True
    config.output.subtitle_punctuation = False
    config.output.subtitle_language = "zh"
    config.output.max_chars = 25
    config.output.subtitle_stem = "test"
    config.asr = SimpleNamespace()
    config.asr.model = "asr_0.6b"
    config.asr.quantization = "q8"
    config.align = SimpleNamespace()
    config.align.model = "aligner"
    config.align.quantization = "q8"
    return config


def test_batch_transcribe_writes_manifest_and_keeps_failed_items(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    """batch-transcribe should write a retryable manifest for mixed results."""
    calls = []

    class FakeRunner:
        def run_pipeline(
            self,
            pipeline,
            input_path,
            output_dir,
            fmt="srt",
            enhance="local",
            translate_to=None,
            bilingual="off",
        ):
            calls.append((pipeline.work_dir, input_path, output_dir, fmt))
            return {"output_dir": str(output_dir), "timings": {"asr": 1.0}}

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.work_dir = work_dir

            class Workspace:
                def ensure_dirs(self):
                    return None

            self.workspace = Workspace()

    monkeypatch.setattr("subtap.ui.tui.RichRunner", FakeRunner)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config", lambda _: _make_mock_config()
    )

    ok_file = tmp_path / "ok.wav"
    missing_file = tmp_path / "missing.wav"
    ok_file.write_bytes(b"ok")
    output_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "batch-transcribe",
            "--files",
            f"{ok_file},{missing_file}",
            "--output-dir",
            str(output_dir),
            "--json",
            "--no-confirm",
        ],
    )

    assert result.exit_code == 0

    # JSON output is now streaming (JSON Lines)
    lines = result.output.strip().split("\n")
    assert len(lines) >= 3  # start, item_complete(s), complete

    # Check start
    start = json.loads(lines[0])
    assert start["type"] == "start"
    assert start["total"] == 2

    # Check complete
    complete = json.loads(lines[-1])
    assert complete["type"] == "complete"
    assert complete["ok"] is False
    assert complete["succeeded"] == 1
    assert complete["failed"] == 1

    # Check manifest
    manifest = output_dir / "manifest.json"
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert saved["version"] == 2
    assert saved["ok"] is False
    statuses = [item["status"] for item in saved["items"]]
    assert "succeeded" in statuses
    assert "failed" in statuses
    assert saved["items"][1]["error"] == "文件不存在"
    assert len(calls) == 1


def test_batch_transcribe_stops_before_output_when_models_are_missing(
    tmp_path, monkeypatch
):
    from subtap.schemas.config import SubtapConfig

    config = SubtapConfig()
    config.models.root = str(tmp_path / "models")
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
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

    assert result.exit_code == 1
    assert "必需模型未就绪" in result.output
    assert not output.exists()


def test_batch_transcribe_explicit_fast_selects_06b(
    tmp_path, monkeypatch, skip_runtime_model_validation
):
    captured_models = []

    class FakePipeline:
        def __init__(self, config, work_dir):
            captured_models.append(config.asr.model)
            self.work_dir = work_dir
            self.workspace = SimpleNamespace(ensure_dirs=lambda: None)

    class FakeRunner:
        def run_pipeline(self, _pipeline, _input, output_dir, **_kwargs):
            return {"output_dir": str(output_dir), "timings": {}}

    config = _make_mock_config()
    config.asr.model = "asr_1.7b"
    monkeypatch.setattr("subtap.schemas.config.load_config", lambda _: config)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)
    monkeypatch.setattr("subtap.ui.tui.RichRunner", FakeRunner)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"audio")

    result = runner.invoke(
        app,
        [
            "batch-transcribe",
            str(audio),
            "--mode",
            "fast",
            "--output-dir",
            str(tmp_path / "output"),
            "--no-confirm",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert captured_models == ["asr_0.6b"]
