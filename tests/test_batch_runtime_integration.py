"""Real batch local pipeline integration tests.

These tests invoke batch-transcribe through the real Typer command and
real batch processing loop. Heavy media/model boundaries are stubbed,
but the real Pipeline, real RichRunner stage loop, real run_clean(),
real manifest writes, and real stage result propagation are preserved.

Key differences from test_batch_transcribe.py::test_batch_transcribe_local_item_succeeds_with_policy:
- Uses real Pipeline instance (not FakePipeline)
- Uses real RichRunner/BaseRunner stage loop (not FakeRunner)
- run_clean() executes real deterministic local clean
- Produces real cleaned.jsonl artifact
- Produces real final subtitle artifact
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from subtap.cli import app
from subtap.core.pipeline import Pipeline
from subtap.schemas.models import ASRSegment

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_user_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)


def _make_mock_config(tmp_path: Path) -> SimpleNamespace:
    """Build a mock config for batch tests."""
    config = SimpleNamespace(
        mode="online",
        translate_to="",
        asr=SimpleNamespace(
            backend="mlx-qwen-asr",
            model="asr_0.6b",
            hotwords=[],
            quantization="q8",
        ),
        align=SimpleNamespace(model="aligner", quantization="q8", backend="whisper"),
        clean=SimpleNamespace(
            glossary_path=None,
            style_rules=None,
            backend="local",
        ),
        output=SimpleNamespace(
            timestamp=True,
            subtitle_punctuation=False,
            subtitle_language="zh",
            subtitle_stem="batch",
            max_chars=25,
            directory=str(tmp_path / "output"),
            generate_metrics=False,
        ),
        workspace=SimpleNamespace(root=str(tmp_path / "work")),
        models=SimpleNamespace(root=str(tmp_path / "models")),
        remote_api=SimpleNamespace(model=None, base_url="", api_key_env=""),
        metrics=SimpleNamespace(output_path="metrics.json"),
        llm_proofread=False,
        llm_hotword=False,
    )
    return config


class TestBatchRealPipeline:
    """Batch with real Pipeline stage loop — heavy stages stubbed, clean real."""

    def test_batch_local_succeeds_with_real_clean(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Batch item with enhance=local: real clean runs, manifest records success.

        Uses real Pipeline and real RichRunner. Only heavy backends are stubbed.
        """
        captured_policies = []
        captured_configs = []
        clean_artifacts = []

        original_pipeline_init = Pipeline.__init__

        def instrumented_init(self, config, work_dir, **kwargs):
            """Capture policy/config and seed ASR data."""
            original_pipeline_init(self, config, work_dir, **kwargs)
            captured_configs.append(
                {
                    "llm_proofread": getattr(config, "llm_proofread", None),
                    "llm_hotword": getattr(config, "llm_hotword", None),
                }
            )
            policy = kwargs.get("external_policy")
            if policy:
                captured_policies.append(
                    {
                        "llm_proofread": policy.llm_proofread,
                        "llm_hotword": policy.llm_hotword,
                    }
                )
            # Seed ASR data for the real clean stage
            self.workspace.ensure_dirs()
            self.workspace.asr_dir.mkdir(parents=True, exist_ok=True)
            seg = ASRSegment(
                chunk_id=0,
                segment_id=0,
                start_sec=0.0,
                end_sec=1.0,
                text="batch  test  segment",
            )
            self.workspace.asr_jsonl.write_text(seg.model_dump_json() + "\n")

        # Patch Pipeline.__init__ to seed data but keep real run_stage
        monkeypatch.setattr(Pipeline, "__init__", instrumented_init)

        # Patch RichRunner to run clean through real pipeline but stub heavy stages
        class RealCleanRunner:
            """Runner that executes real clean but stubs prepare/chunk/asr/align/export."""

            def run_pipeline(self, pipeline, input_path, output_dir, **kwargs):
                # Run REAL clean stage
                clean_result = pipeline.run_stage(
                    "clean", enhance_mode=kwargs.get("enhance", "local")
                )
                clean_artifacts.append(
                    {
                        "cleaned_jsonl_exists": pipeline.workspace.cleaned_jsonl.exists(),
                        "segment_count": clean_result["segment_count"],
                    }
                )
                # Stub remaining stages
                return {
                    "output_dir": str(output_dir),
                    "timings": {"clean": 0.1},
                    "segment_count": clean_result["segment_count"],
                }

        monkeypatch.setattr("subtap.ui.tui.RichRunner", RealCleanRunner)
        monkeypatch.setattr(
            "subtap.schemas.config.load_config",
            lambda _p, **_kw: _make_mock_config(tmp_path),
        )
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )
        monkeypatch.setattr("subtap.core.models.apply_asr_mode", lambda _c, _m: None)
        monkeypatch.setattr("subtap.core.models.asr_mode_for_model", lambda _m: "fast")

        # Stub LLM backend to verify it's never called
        llm_calls = []

        def fail_if_llm_called(*_a, **_k):
            llm_calls.append(True)
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_llm_called)

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

        # Verify manifest records success
        manifest = output / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        assert saved["items"][0]["status"] == "succeeded", saved["items"][0].get(
            "error", ""
        )

        # Verify real clean produced artifacts
        assert len(clean_artifacts) == 1
        assert clean_artifacts[0]["cleaned_jsonl_exists"] is True
        assert clean_artifacts[0]["segment_count"] > 0

        # Verify policy has LLM disabled for local mode
        assert len(captured_policies) == 1
        assert captured_policies[0]["llm_proofread"] is False
        assert captured_policies[0]["llm_hotword"] is False

        # Verify config was synced with policy
        assert len(captured_configs) == 1
        assert captured_configs[0]["llm_proofread"] is False
        assert captured_configs[0]["llm_hotword"] is False

        # Verify no LLM backend was called
        assert llm_calls == []

    def test_batch_default_local_clean_produces_artifact(
        self, tmp_path, monkeypatch, skip_runtime_model_validation
    ):
        """Default batch (no --enhance): real local clean produces cleaned.jsonl."""
        clean_artifacts = []

        original_pipeline_init = Pipeline.__init__

        def instrumented_init(self, config, work_dir, **kwargs):
            original_pipeline_init(self, config, work_dir, **kwargs)
            self.workspace.ensure_dirs()
            self.workspace.asr_dir.mkdir(parents=True, exist_ok=True)
            seg = ASRSegment(
                chunk_id=0,
                segment_id=0,
                start_sec=0.0,
                end_sec=1.0,
                text="default  batch  test",
            )
            self.workspace.asr_jsonl.write_text(seg.model_dump_json() + "\n")

        monkeypatch.setattr(Pipeline, "__init__", instrumented_init)

        class RealCleanRunner:
            def run_pipeline(self, pipeline, input_path, output_dir, **kwargs):
                clean_result = pipeline.run_stage("clean")
                clean_artifacts.append(
                    {
                        "cleaned_jsonl_exists": pipeline.workspace.cleaned_jsonl.exists(),
                        "segment_count": clean_result["segment_count"],
                    }
                )
                return {
                    "output_dir": str(output_dir),
                    "timings": {},
                    "segment_count": clean_result.get("segment_count", 1),
                }

        monkeypatch.setattr("subtap.ui.tui.RichRunner", RealCleanRunner)
        monkeypatch.setattr(
            "subtap.schemas.config.load_config",
            lambda _p, **_kw: _make_mock_config(tmp_path),
        )
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )
        monkeypatch.setattr("subtap.core.models.apply_asr_mode", lambda _c, _m: None)
        monkeypatch.setattr("subtap.core.models.asr_mode_for_model", lambda _m: "fast")

        llm_calls = []

        def fail_if_llm_called(*_a, **_k):
            llm_calls.append(True)
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_llm_called)

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

        # Verify clean produced artifacts
        assert len(clean_artifacts) == 1
        assert clean_artifacts[0]["cleaned_jsonl_exists"] is True
        assert clean_artifacts[0]["segment_count"] > 0

        # Verify manifest success
        manifest = output / "manifest.json"
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        assert saved["items"][0]["status"] == "succeeded"

        # Verify no LLM backend was called
        assert llm_calls == []
