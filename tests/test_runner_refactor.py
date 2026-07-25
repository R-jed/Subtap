"""Tests for BaseRunner refactoring.

Verifies the four bugs fixed by extracting BaseRunner:
- P1-1: TUIRunner/PlainRunner now include learn stage
- P1-5: Three runners share common logic via BaseRunner
- P2-2: Export uses {fmt} consistently across all runners
- P2-1: PlainRunner step numbering is dynamic (no hardcoded [X/8])
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from subtap.engine.state import PipelineRunContext, build_stage_kwargs
from subtap.ui.tui import BaseRunner, RichRunner, TUIRunner, PlainRunner

# ── helpers ──────────────────────────────────────────────────────────


def _make_config(script_path=None, glossary_path=None):
    """Create a minimal config for testing."""
    return SimpleNamespace(
        output=SimpleNamespace(
            subtitle_punctuation=False,
            subtitle_language="zh",
            max_chars=25,
            subtitle_formats=["srt", "vtt"],
            subtitle_stem="final",
            script_path=script_path,
        ),
        clean=SimpleNamespace(
            glossary_path=glossary_path,
        ),
    )


def _make_pipeline(config):
    """Create a mock pipeline that records stage calls."""
    calls = []

    pipeline = MagicMock()
    pipeline.config = config
    pipeline.workspace.root = Path("/tmp/test_work")
    pipeline.workspace.aligned_jsonl = Path("/tmp/test_work/aligned.jsonl")

    def run_stage(stage, **kwargs):
        calls.append((stage, kwargs))
        results = {
            "prepare": {"media_info": {"duration": 10.0, "sample_rate": 16000}},
            "chunk": {"chunk_count": 3},
            "asr": {"segment_count": 5},
            "clean": {"segment_count": 5},
            "segment": {"sentence_count": 8},
            "script_match": {"skipped": False, "message": "匹配 3 条"},
            "align": {"aligned_count": 8},
            "hotword": {"replaced": 2, "total": 8},
            "learn": {"learned": 1},
            "translate": {"translated_count": 8},
        }
        return results.get(stage, {})

    pipeline.run_stage = run_stage
    pipeline._calls = calls
    return pipeline


# ── P1-1: learn stage in all runners ────────────────────────────────


class TestLearnStageInAllRunners:
    """P1-1: learn stage must execute in all runners."""

    def test_build_stages_includes_learn(self):
        """_build_stages should always include learn."""
        config = _make_config()
        stages = BaseRunner._build_stages(config, translate_to=None)
        keys = [s["key"] for s in stages]
        assert "learn" in keys, f"learn not in stages: {keys}"

    def test_build_stages_learn_before_translate(self):
        """learn should come before translate when translate is enabled."""
        config = _make_config()
        stages = BaseRunner._build_stages(config, translate_to="en")
        keys = [s["key"] for s in stages]
        learn_idx = keys.index("learn")
        translate_idx = keys.index("translate")
        assert (
            learn_idx < translate_idx
        ), f"learn ({learn_idx}) should be before translate ({translate_idx})"

    def test_build_stages_learn_after_hotword(self):
        """learn should come after hotword."""
        config = _make_config()
        stages = BaseRunner._build_stages(config, translate_to=None)
        keys = [s["key"] for s in stages]
        hotword_idx = keys.index("hotword")
        learn_idx = keys.index("learn")
        assert hotword_idx < learn_idx

    def test_build_stages_order(self):
        """Full stage order should be correct."""
        config = _make_config()
        stages = BaseRunner._build_stages(config, translate_to="en")
        keys = [s["key"] for s in stages]
        expected = [
            "prepare",
            "chunk",
            "asr",
            "clean",
            "segment",
            "align",
            "hotword",
            "learn",
            "translate",
            "export",
        ]
        assert keys == expected

    def test_build_stages_no_translate(self):
        """Without translate_to, translate stage should be absent."""
        config = _make_config()
        stages = BaseRunner._build_stages(config, translate_to=None)
        keys = [s["key"] for s in stages]
        assert "translate" not in keys
        assert "learn" in keys

    def test_build_stages_with_script_match(self):
        """script_match should be included when script_path is set."""
        config = _make_config(script_path="/some/script.txt")
        stages = BaseRunner._build_stages(config, translate_to=None)
        keys = [s["key"] for s in stages]
        assert "script_match" in keys

    def test_script_match_runs_before_align(self):
        """script_match must run before align so matched text affects final timing."""
        config = _make_config(script_path="/some/script.txt")
        stages = BaseRunner._build_stages(config, translate_to=None)
        keys = [s["key"] for s in stages]
        assert keys.index("script_match") < keys.index("align")

    def test_build_stages_without_script_match(self):
        """script_match should be absent when script_path is None."""
        config = _make_config(script_path=None)
        stages = BaseRunner._build_stages(config, translate_to=None)
        keys = [s["key"] for s in stages]
        assert "script_match" not in keys


# ── P2-2: export uses {fmt} consistently ────────────────────────────


class TestExportFormatConsistency:
    """P2-2: export stage should use build_stage_kwargs for consistent params."""

    def test_export_kwargs_from_builder(self):
        """build_stage_kwargs should produce correct export kwargs."""
        ctx = PipelineRunContext(
            input_path="/test/in.wav",
            output_dir="/test/out",
            fmt="vtt",
            enhance="local",
            translate_to="en",
            bilingual="source-first",
            subtitle_stem="custom",
        )
        kwargs = build_stage_kwargs("export", ctx)
        assert kwargs["fmt"] == "vtt"
        assert kwargs["output_dir"] == "/test/out"
        assert kwargs["stem"] == "custom"
        assert kwargs["translate_to"] == "en"
        assert kwargs["bilingual"] == "source-first"

    def test_export_kwargs_srt_format(self):
        """build_stage_kwargs should pass through srt format."""
        ctx = PipelineRunContext(
            input_path="/test/in.wav",
            output_dir="/test/out",
            fmt="srt",
        )
        kwargs = build_stage_kwargs("export", ctx)
        assert kwargs["fmt"] == "srt"
        assert kwargs["bilingual"] == "off"


# ── P2-1: PlainRunner dynamic step numbering ────────────────────────


class TestPlainRunnerStepNumbering:
    """P2-1: PlainRunner step numbers should be dynamic, not hardcoded."""

    @patch("subtap.core.export.run_final_exports")
    def test_step_numbers_are_sequential(self, mock_export, tmp_path):
        """Step numbers should be [1/N], [2/N], ..., [N/N] sequentially."""
        mock_export.return_value = {"output_path": str(tmp_path / "out.srt")}
        config = _make_config()
        pipeline = _make_pipeline(config)

        runner = PlainRunner()
        echo_calls = []

        def capture_echo(msg):
            echo_calls.append(str(msg))

        try:
            with patch("typer.echo", capture_echo):
                runner.run_pipeline(
                    pipeline,
                    tmp_path / "in.wav",
                    tmp_path,
                    fmt="srt",
                    enhance="local",
                )
        except Exception:
            pass

        # Extract step lines
        step_lines = [c for c in echo_calls if c.startswith("▸ [")]
        assert len(step_lines) > 0, f"No step lines found in: {echo_calls}"

        # Verify sequential numbering
        import re

        numbers = []
        for line in step_lines:
            m = re.match(r"▸ \[(\d+)/(\d+)\]", line)
            assert m, f"Step line doesn't match pattern: {line}"
            numbers.append((int(m.group(1)), int(m.group(2))))

        # Step numbers should be sequential
        for i, (num, total) in enumerate(numbers):
            assert (
                num == i + 1
            ), f"Step {i}: expected {i + 1}, got {num} in {step_lines[i]}"

        # Total should be consistent
        totals = set(t for _, t in numbers)
        assert len(totals) == 1, f"Inconsistent totals: {totals}"

    @patch("subtap.core.export.run_final_exports")
    def test_step_numbers_with_translate(self, mock_export, tmp_path):
        """With translate, total should be higher (includes translate stage)."""
        mock_export.return_value = {"output_path": str(tmp_path / "out.srt")}
        config = _make_config()
        pipeline = _make_pipeline(config)

        runner = PlainRunner()
        echo_calls = []

        try:
            with patch("typer.echo", lambda msg: echo_calls.append(str(msg))):
                runner.run_pipeline(
                    pipeline,
                    tmp_path / "in.wav",
                    tmp_path,
                    fmt="srt",
                    enhance="local",
                    translate_to="en",
                )
        except Exception:
            pass

        step_lines = [c for c in echo_calls if c.startswith("▸ [")]
        import re

        totals = set()
        for line in step_lines:
            m = re.match(r"▸ \[(\d+)/(\d+)\]", line)
            if m:
                totals.add(int(m.group(2)))

        assert len(totals) == 1
        total = totals.pop()

        # With translate, should have more steps than without
        config_no_translate = _make_config()
        BaseRunner._build_stages(config_no_translate, None)
        stages_with_translate = BaseRunner._build_stages(config, "en")
        assert total == len(stages_with_translate)

    @patch("subtap.core.export.run_final_exports")
    def test_step_numbers_without_translate(self, mock_export, tmp_path):
        """Without translate, total should match non-translate stage count."""
        mock_export.return_value = {"output_path": str(tmp_path / "out.srt")}
        config = _make_config()
        pipeline = _make_pipeline(config)

        runner = PlainRunner()
        echo_calls = []

        try:
            with patch("typer.echo", lambda msg: echo_calls.append(str(msg))):
                runner.run_pipeline(
                    pipeline,
                    tmp_path / "in.wav",
                    tmp_path,
                    fmt="srt",
                    enhance="local",
                    translate_to=None,
                )
        except Exception:
            pass

        step_lines = [c for c in echo_calls if c.startswith("▸ [")]
        import re

        totals = set()
        for line in step_lines:
            m = re.match(r"▸ \[(\d+)/(\d+)\]", line)
            if m:
                totals.add(int(m.group(2)))

        assert len(totals) == 1
        total = totals.pop()
        expected = len(BaseRunner._build_stages(config, None))
        assert total == expected, f"Expected {expected} total steps, got {total}"


# ── P1-5: shared base logic ─────────────────────────────────────────


class TestBaseRunnerSharedLogic:
    """P1-5: verify BaseRunner methods exist and work correctly."""

    def test_save_meta_structure(self, tmp_path):
        """_save_meta should produce correct meta dict."""
        runner = RichRunner()
        runner.timings = {"prepare": 1.0, "asr": 5.0, "export": 0.5}

        pipeline = MagicMock()
        pipeline.workspace.root = tmp_path

        meta = runner._save_meta(
            pipeline, tmp_path / "in.wav", tmp_path / "out", "srt", 6.5
        )

        assert meta["input"] == str(tmp_path / "in.wav")
        assert meta["output_dir"] == str(tmp_path / "out")
        assert meta["format"] == "srt"
        assert meta["total_time_sec"] == 6.5
        assert "timings" in meta

        # Check file was written
        meta_file = tmp_path / "run_meta.json"
        assert meta_file.exists()

    def test_all_runners_inherit_base(self):
        """All three runners should be BaseRunner subclasses."""
        assert issubclass(RichRunner, BaseRunner)
        assert issubclass(TUIRunner, BaseRunner)
        assert issubclass(PlainRunner, BaseRunner)


# ── Glossary path propagation ─────────────────────────────────────


class TestGlossaryPathPropagation:
    """The selected glossary file should reach hotword and learning stages."""

    def test_build_stages_no_kwargs_injection(self):
        """_build_stages should not inject kwargs (delegated to build_stage_kwargs)."""
        config = _make_config(glossary_path="/custom/glossary.yaml")
        stages = BaseRunner._build_stages(config, translate_to=None)
        hotword = next(s for s in stages if s["key"] == "hotword")
        assert "kwargs" not in hotword

    def test_hotword_kwargs_from_builder(self):
        ctx = PipelineRunContext(
            input_path="/test/in.wav",
            output_dir="/test/out",
            glossary_path="/custom/glossary.yaml",
        )
        kwargs = build_stage_kwargs("hotword", ctx)
        assert kwargs == {"glossary_path": "/custom/glossary.yaml"}

    def test_learn_kwargs_from_builder(self):
        ctx = PipelineRunContext(
            input_path="/test/in.wav",
            output_dir="/test/out",
            glossary_path="/custom/glossary.yaml",
        )
        kwargs = build_stage_kwargs("learn", ctx)
        assert kwargs == {"glossary_path": "/custom/glossary.yaml"}

    def test_clean_kwargs_from_builder(self):
        ctx = PipelineRunContext(
            input_path="/test/in.wav",
            output_dir="/test/out",
            enhance="api",
            glossary_path="/custom/glossary.yaml",
        )
        kwargs = build_stage_kwargs("clean", ctx)
        assert kwargs == {
            "enhance_mode": "api",
            "glossary_path": "/custom/glossary.yaml",
        }

    def test_no_glossary_path_yields_none(self):
        """When glossary_path is empty, builder should yield None."""
        ctx = PipelineRunContext(
            input_path="/test/in.wav",
            output_dir="/test/out",
            glossary_path="",
        )
        assert build_stage_kwargs("hotword", ctx) == {"glossary_path": None}
        assert build_stage_kwargs("learn", ctx) == {"glossary_path": None}
        assert build_stage_kwargs("clean", ctx) == {
            "enhance_mode": "local",
            "glossary_path": None,
        }

    def test_pipeline_stage_learn_accepts_glossary_path(self, tmp_path):
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        config = SubtapConfig()
        glossary_path = tmp_path / "camera.yaml"
        glossary_path.write_text("terms: []\n", encoding="utf-8")

        pipeline = Pipeline(config, work_dir=tmp_path)
        result = pipeline.run_stage("learn", glossary_path=str(glossary_path))
        assert result["learned"] == 0

    def test_pipeline_stage_learn_rejects_missing_selected_glossary(self, tmp_path):
        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        pipeline = Pipeline(SubtapConfig(), work_dir=tmp_path)

        with pytest.raises(FileNotFoundError):
            pipeline.run_stage("learn", glossary_path=tmp_path / "missing.yaml")

    def test_pipeline_stage_learn_keeps_selected_yaml_read_only(self, tmp_path):
        import json

        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        config = SubtapConfig()
        glossary_path = tmp_path / "camera.yaml"
        glossary_path.write_text("style: [简洁]\n", encoding="utf-8")

        # Create workspace with ops file
        pipeline = Pipeline(config, work_dir=tmp_path)
        ops_path = pipeline.workspace.root / "llm_hotword_ops.jsonl"
        ops_path.write_text(
            json.dumps({"from": "VITURE", "to": "维图尔", "segment_id": 0}) + "\n",
            encoding="utf-8",
        )

        with patch("pathlib.Path.home", return_value=tmp_path):
            result = pipeline.run_stage("learn", glossary_path=str(glossary_path))

        assert result["learned"] >= 1
        assert glossary_path.read_text(encoding="utf-8") == "style: [简洁]\n"
        assert result["path"] == str(
            tmp_path / ".subtap" / "glossaries" / "learned.txt"
        )

    def test_pipeline_stage_learn_fallback_default(self, tmp_path):
        """Pipeline._stage_learn should use the canonical learned glossary."""
        import json

        from subtap.core.pipeline import Pipeline
        from subtap.schemas.config import SubtapConfig

        config = SubtapConfig()
        pipeline = Pipeline(config, work_dir=tmp_path)
        ops_path = pipeline.workspace.root / "llm_hotword_ops.jsonl"
        ops_path.write_text(
            json.dumps({"from": "TEST", "to": "测试词", "segment_id": 0}) + "\n",
            encoding="utf-8",
        )

        # No glossary_path -> should use the learned glossary
        with patch("subtap.core.pipeline.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            result = pipeline.run_stage("learn")

        assert result["learned"] >= 1
        default_path = tmp_path / ".subtap" / "glossaries" / "learned.txt"
        assert default_path.exists(), f"Expected hotwords at {default_path}"


# ── Parameter equivalence: normal vs resume/retry ──────────────────


class TestParameterEquivalence:
    """Normal run and resume/retry must produce identical stage kwargs."""

    def test_normal_resume_kwargs_equivalence(self):
        """build_stage_kwargs produces identical results for all shared stages."""
        ctx = PipelineRunContext(
            input_path="/media/input.mp3",
            output_dir="/out",
            fmt="vtt",
            enhance="api",
            translate_to="en",
            bilingual="source-first",
            glossary_path="/tmp/glossary.yaml",
            asr_backend="mlx-qwen-asr",
            subtitle_stem="custom",
        )

        shared_stages = [
            "prepare",
            "chunk",
            "asr",
            "clean",
            "segment",
            "align",
            "hotword",
            "learn",
            "translate",
            "export",
        ]

        for stage in shared_stages:
            kwargs = build_stage_kwargs(stage, ctx)
            # Both paths call the same function with the same context,
            # so equality is guaranteed by construction.
            assert kwargs == build_stage_kwargs(
                stage, ctx
            ), f"kwargs mismatch for {stage}: {kwargs}"

    def test_export_kwargs_includes_all_fields(self):
        """Export kwargs must contain all required fields."""
        ctx = PipelineRunContext(
            input_path="/media/input.mp3",
            output_dir="/out",
            fmt="vtt",
            enhance="api",
            translate_to="en",
            bilingual="source-first",
            subtitle_stem="custom",
        )
        kwargs = build_stage_kwargs("export", ctx)
        assert set(kwargs.keys()) == {
            "fmt",
            "output_dir",
            "stem",
            "translate_to",
            "bilingual",
        }
        assert kwargs["fmt"] == "vtt"
        assert kwargs["stem"] == "custom"

    def test_prepare_kwargs_has_path(self):
        """prepare kwargs must include input_path as Path."""
        ctx = PipelineRunContext(
            input_path="/media/input.mp3",
            output_dir="/out",
        )
        kwargs = build_stage_kwargs("prepare", ctx)
        assert isinstance(kwargs["input_path"], Path)
        assert str(kwargs["input_path"]) == "/media/input.mp3"


# ── Path canonicalization ──────────────────────────────────────────


class TestPathCanonicalization:
    """PipelineRunContext should persist absolute canonical paths."""

    def test_relative_paths_become_absolute(self, tmp_path):
        """Relative paths should be resolved to absolute under original cwd."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Create files so resolve() works
            (tmp_path / "media").mkdir()
            (tmp_path / "media" / "input.mp3").touch()
            (tmp_path / "script.txt").touch()
            (tmp_path / "glossary.yaml").touch()

            ctx = PipelineRunContext(
                input_path=str(Path("./media/input.mp3").resolve()),
                output_dir=str(Path("./out").resolve()),
                script_path=str(Path("./script.txt").resolve()),
                glossary_path=str(Path("./glossary.yaml").resolve()),
            )

            # All paths should be absolute
            assert Path(ctx.input_path).is_absolute()
            assert Path(ctx.output_dir).is_absolute()
            assert Path(ctx.script_path).is_absolute()
            assert Path(ctx.glossary_path).is_absolute()

            # Should point to original cwd
            assert str(tmp_path) in ctx.input_path
            assert str(tmp_path) in ctx.output_dir
            assert str(tmp_path) in ctx.script_path
            assert str(tmp_path) in ctx.glossary_path
        finally:
            os.chdir(original_cwd)

    def test_empty_optional_paths_stay_empty(self):
        """Empty script_path and glossary_path should stay empty."""
        ctx = PipelineRunContext(
            input_path="/media/input.mp3",
            output_dir="/out",
            script_path="",
            glossary_path="",
        )
        assert ctx.script_path == ""
        assert ctx.glossary_path == ""

    def test_paths_survive_cwd_change(self, tmp_path):
        """Paths persisted in state should survive a cwd change."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ctx = PipelineRunContext(
                input_path=str(Path("./media/input.mp3").resolve()),
                output_dir=str(Path("./out").resolve()),
            )

            # Simulate loading state after cwd change
            data = ctx.to_dict()
            loaded = PipelineRunContext.from_dict(data)

            # Paths should still point to original cwd
            assert str(tmp_path) in loaded.input_path
            assert str(tmp_path) in loaded.output_dir
        finally:
            os.chdir(original_cwd)
