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

import pytest
from typer.testing import CliRunner

from subtap.cli import app
from subtap.core.pipeline import Pipeline
from tests.fixtures.pipeline_stubs import (
    make_instrumented_init as _make_instrumented_init,
    seed_asr as _seed_asr,
    stub_align as _stub_align,
    stub_asr as _stub_asr,
    stub_chunks as _stub_chunks,
    stub_hotword as _stub_hotword,
    stub_prepare as _stub_prepare,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


class TestBatchRealRunner:
    """Batch with real Pipeline and real RichRunner stage loop."""

    def test_batch_local_succeeds_with_real_runner(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Batch item with enhance=local: real runner drives full pipeline through export."""
        original_init = Pipeline.__init__
        instrumented = _make_instrumented_init(original_init, ["batch  test  segment"])

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

        # Intercept cleanroom.clean_intermediate_files to record cleaned.jsonl
        # existence BEFORE it gets deleted by cleanup
        from subtap.engine.cleanroom import Cleanroom

        original_clean_intermediate = Cleanroom.clean_intermediate_files
        cleaned_existed_before_cleanup: list[bool] = []

        def intercepting_clean_intermediate(self):
            cleaned_path = self.root / "cleaned.jsonl"
            cleaned_existed_before_cleanup.append(cleaned_path.is_file())
            return original_clean_intermediate(self)

        monkeypatch.setattr(
            Cleanroom, "clean_intermediate_files", intercepting_clean_intermediate
        )

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

        # Verify cleaned.jsonl existed before cleanup ran
        assert len(cleaned_existed_before_cleanup) == 1
        assert (
            cleaned_existed_before_cleanup[0] is True
        ), "cleaned.jsonl must exist before cleanroom cleanup"

        # Verify surviving artifacts (cleaned.jsonl and sentences.jsonl are
        # deleted by cleanroom.clean_intermediate_files() after successful batch)
        item_work = output / "voice_wav" / "work"
        assert not (
            item_work / "cleaned.jsonl"
        ).exists(), "cleaned.jsonl should be deleted by cleanup"
        assert (item_work / "aligned.jsonl").exists()

        # Verify final subtitle exists, is non-empty, and contains cleaned text
        srt_path = output / "voice_wav" / "voice.srt"
        assert srt_path.exists()
        srt_text = srt_path.read_text()
        assert srt_text.strip()

        # Verify SRT contains cleaned (single-space) text, not original double-space
        assert "batch test" in srt_text.lower()
        assert (
            "batch  test" not in srt_text.lower()
        ), f"SRT still contains uncleaned double-space text: {srt_text[:200]}"

        # Verify no LLM backend was called
        assert llm_calls == []

        # Verify no external disclosure text for local execution
        assert "发送" not in result.output

    def test_batch_item_policy_and_config_flags(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Batch item policy and config flags are set correctly."""
        # Capture policy/config from Pipeline.__init__
        captured_policies = []
        captured_configs = []
        original_init = Pipeline.__init__

        def instrumented_with_capture(self, config, work_dir, **kwargs):
            original_init(self, config, work_dir, **kwargs)
            self.workspace.ensure_dirs()
            _seed_asr(self.workspace, ["policy  test"])
            if kwargs.get("external_policy") is not None:
                captured_policies.append(kwargs["external_policy"])
                captured_configs.append(config)

        monkeypatch.setattr(Pipeline, "__init__", instrumented_with_capture)
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

        # Verify policy and config were captured
        assert len(captured_policies) == 1
        assert len(captured_configs) == 1

        policy = captured_policies[0]
        config = captured_configs[0]

        # Verify local enhance mode → LLM features disabled
        assert policy.llm_proofread is False
        assert policy.llm_hotword is False
        assert config.llm_proofread is False
        assert config.llm_hotword is False

    def test_batch_default_local_clean_produces_artifact(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Default batch (no --enhance): real local clean produces artifacts."""
        original_init = Pipeline.__init__
        instrumented = _make_instrumented_init(original_init, ["default  batch  test"])

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

        # Verify final subtitle contains cleaned text, not double-space original
        srt_path = output / "voice_wav" / "voice.srt"
        assert srt_path.exists()
        srt_text = srt_path.read_text()
        assert srt_text.strip()
        assert "default batch test" in srt_text.lower()
        assert (
            "default  batch  test" not in srt_text.lower()
        ), f"SRT still contains uncleaned double-space text: {srt_text[:200]}"

        assert llm_calls == []
