"""Real runner-driven local pipeline integration tests.

These tests exercise the actual production orchestration path:

    real RichRunner.run_pipeline()
        → BaseRunner._run_pipeline_inner()
            → _build_stages()
            → _run_loop()
                → Pipeline.run_stage() for each stage
            → _run_export()

Heavy backends (prepare_media, split_chunks, run_asr, run_align) are
stubbed at their function boundaries.  run_clean, segment, hotword,
learn, and export execute real production code.

The align stub reads the ACTUAL sentences.jsonl produced by the real
segment stage — final.srt is causally derived from the real clean and
segment output.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from subtap.core.pipeline import Pipeline
from subtap.schemas.config import SubtapConfig
from subtap.ui.tui import RichRunner
from tests.fixtures.pipeline_stubs import (
    seed_asr as _seed_asr,
    stub_align as _stub_align,
    stub_asr as _stub_asr,
    stub_chunks_duration as _stub_chunks_duration,
    stub_hotword as _stub_hotword,
    stub_prepare_duration as _stub_prepare_duration,
)

runner = CliRunner()


# ── helpers ─────────────────────────────────────────────────────────


def _make_config(tmp_path: Path) -> SubtapConfig:
    """Build a minimal SubtapConfig for pipeline tests."""
    config = SubtapConfig()
    config.workspace.root = str(tmp_path / "work")
    config.output.directory = str(tmp_path / "output")
    return config


# ── tests ───────────────────────────────────────────────────────────


class TestRunnerDrivenPipeline:
    """Execute real pipeline through the real runner stage loop.

    The runner constructs the stage plan, iterates stages, and calls
    Pipeline.run_stage() for each one.  Heavy backends are stubbed;
    run_clean and segment execute real production code.
    """

    def _run_full_pipeline(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        enhance: str = "local",
        local_only: bool = False,
    ) -> tuple[list[str], Path]:
        """Run full pipeline through real runner.  Return (observed_stages, output_dir)."""
        config = _make_config(tmp_path)
        work_dir = tmp_path / "work"
        output_dir = tmp_path / "output"

        # Seed ASR data in Pipeline.__init__
        original_init = Pipeline.__init__

        def seeded_init(self, config, work_dir, **kwargs):
            original_init(self, config, work_dir, **kwargs)
            self.workspace.ensure_dirs()
            _seed_asr(self.workspace, ["hello  world  test", "foo  bar  baz"])

        monkeypatch.setattr(Pipeline, "__init__", seeded_init)

        # Stub heavy backends
        monkeypatch.setattr(
            "subtap.core.media.prepare_media", _stub_prepare_duration(2.0)
        )
        monkeypatch.setattr(
            "subtap.core.vad.split_chunks", _stub_chunks_duration(tmp_path, 2.0)
        )
        monkeypatch.setattr("subtap.core.asr.run_asr", _stub_asr)
        monkeypatch.setattr("subtap.core.align.run_align", _stub_align)
        monkeypatch.setattr("subtap.core.hotword.run_hotword", _stub_hotword)

        # Prevent LLM backend calls
        def fail_if_llm(*_a, **_k):
            raise AssertionError("get_llm_backend must not be called")

        monkeypatch.setattr("subtap.core.clean.get_llm_backend", fail_if_llm)

        # Stub model validation
        monkeypatch.setattr(
            "subtap.core.models.validate_runtime_models", lambda _c: None
        )
        monkeypatch.setattr("subtap.core.models.apply_asr_mode", lambda _c, _m: None)
        monkeypatch.setattr("subtap.core.models.asr_mode_for_model", lambda _m: "fast")

        # Observe stage order via Pipeline.run_stage spy
        observed: list[str] = []
        original_run_stage = Pipeline.run_stage

        def observed_run_stage(self, stage, **kwargs):
            observed.append(stage)
            return original_run_stage(self, stage, **kwargs)

        monkeypatch.setattr(Pipeline, "run_stage", observed_run_stage)

        # Build policy
        from subtap.runtime.external_policy import build_policy

        policy = build_policy(
            local_only=local_only,
            enhance_mode=enhance,
            asr_backend="mlx-qwen-asr",
        )
        config.llm_proofread = policy.llm_proofread
        config.llm_hotword = policy.llm_hotword

        # Create real Pipeline
        pipeline = Pipeline(
            config,
            work_dir=work_dir,
            external_policy=policy,
        )

        # Create real input file
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"fake-wav-data")

        # Run through real RichRunner
        rich = RichRunner()
        rich.run_pipeline(
            pipeline,
            audio,
            output_dir,
            fmt="srt",
            enhance=enhance,
        )

        return observed, output_dir

    # Expected complete stage order for config without script_path/translate
    _EXPECTED_STAGES = [
        "prepare",
        "chunk",
        "asr",
        "clean",
        "segment",
        "align",
        "hotword",
        "learn",
        "export",
    ]

    @pytest.mark.parametrize(
        "enhance,local_only",
        [
            ("local", False),
            ("api", True),
            ("off", False),
        ],
        ids=["enhance=local", "local_only=True", "enhance=off"],
    )
    def test_full_pipeline_through_runner(
        self, tmp_path, monkeypatch, skip_runtime_model_validation, enhance, local_only
    ):
        """Full runner-driven pipeline: clean → segment → export produces SRT."""
        observed, output_dir = self._run_full_pipeline(
            tmp_path, monkeypatch, enhance=enhance, local_only=local_only
        )

        # Verify observed stages match expected complete order exactly
        assert observed == self._EXPECTED_STAGES

        # Verify artifacts
        work_dir = tmp_path / "work"
        assert (work_dir / "cleaned.jsonl").exists()
        assert (work_dir / "sentences.jsonl").exists()
        assert (work_dir / "aligned.jsonl").exists()

        # Verify final SRT
        srt_path = output_dir / "final.srt"
        assert srt_path.exists()
        srt_text = srt_path.read_text()
        assert srt_text.strip()

        # Verify causal chain: cleaned text appears in SRT
        # Input had "hello  world  test" — real run_clean normalizes
        # double spaces to single.  SRT must contain cleaned form,
        # and must NOT contain the original double-space form.
        srt_lower = srt_text.lower()
        assert "hello world" in srt_lower
        assert (
            "hello  world" not in srt_lower
        ), f"SRT still contains uncleaned double-space text: {srt_text[:200]}"

        # Verify LLM was never called
        # (fail_if_llm raises AssertionError if called)
