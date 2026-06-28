"""Tests for productized batch transcription manifest."""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def test_batch_transcribe_writes_manifest_and_keeps_failed_items(tmp_path, monkeypatch):
    """batch-transcribe should write a retryable manifest for mixed results."""
    calls = []

    class FakeRunner:
        def run_pipeline(
            self, pipeline, input_path, output_dir, fmt="srt", align_enabled=True
        ):
            calls.append(
                (pipeline.work_dir, input_path, output_dir, fmt, align_enabled)
            )
            return {"output_dir": str(output_dir), "timings": {"asr": 1.0}}

    class FakePipeline:
        def __init__(self, _config, work_dir):
            self.work_dir = work_dir

            class Workspace:
                def ensure_dirs(self):
                    return None

            self.workspace = Workspace()

    monkeypatch.setattr("subtap.ui.tui.PlainRunner", FakeRunner)
    monkeypatch.setattr("subtap.core.pipeline.Pipeline", FakePipeline)
    monkeypatch.setattr(
        "subtap.schemas.config.load_config", lambda _: SimpleNamespace()
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
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    manifest = output_dir / "manifest.json"
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["manifest_path"] == str(manifest)
    assert saved["ok"] is False
    assert [item["status"] for item in saved["items"]] == ["succeeded", "failed"]
    assert saved["items"][1]["error"] == "文件不存在"
    assert len(calls) == 1
