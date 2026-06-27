"""Tests for task module — Task abstraction and one-command execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from subtap.task.task import Task


@pytest.fixture
def sample_audio(tmp_path: Path) -> Path:
    """Create a minimal audio file for testing."""
    audio_path = tmp_path / "test.mp3"
    audio_path.write_bytes(b"\x00" * 100)  # Minimal file
    return audio_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return out


# ── Task Initialization ─────────────────────────────────────


class TestTaskInit:
    """Test Task initialization and defaults."""

    def test_task_requires_input_file(self, sample_audio: Path):
        task = Task(input_file=sample_audio)
        assert task.input_file == sample_audio

    def test_task_default_mode(self, sample_audio: Path):
        task = Task(input_file=sample_audio)
        assert task.mode == "hybrid"

    def test_task_default_format(self, sample_audio: Path):
        task = Task(input_file=sample_audio)
        assert task.output_format == "srt"

    def test_task_default_language(self, sample_audio: Path):
        task = Task(input_file=sample_audio)
        assert task.language == "zh"

    def test_task_custom_mode(self, sample_audio: Path):
        task = Task(input_file=sample_audio, mode="fast")
        assert task.mode == "fast"

    def test_task_custom_format(self, sample_audio: Path):
        task = Task(input_file=sample_audio, output_format="vtt")
        assert task.output_format == "vtt"


# ── Task Mode Mapping ───────────────────────────────────────


class TestTaskMode:
    """Test mode to policy mapping."""

    def test_fast_mode_skips_llm(self, sample_audio: Path):
        task = Task(input_file=sample_audio, mode="fast")
        assert task.should_skip_clean is True

    def test_quality_mode_full_pipeline(self, sample_audio: Path):
        task = Task(input_file=sample_audio, mode="quality")
        assert task.should_skip_clean is False
        assert task.should_skip_align is False

    def test_hybrid_mode_enables_clean(self, sample_audio: Path):
        task = Task(input_file=sample_audio, mode="hybrid")
        assert task.should_skip_clean is False


# ── Task Output Structure ───────────────────────────────────


class TestTaskOutput:
    """Test output directory structure creation."""

    def test_creates_output_dir(self, sample_audio: Path, output_dir: Path):
        task = Task(input_file=sample_audio)
        result = task.create_output_structure(output_dir)
        assert result.final_path.parent == output_dir
        assert output_dir.exists()

    def test_creates_final_srt_path(self, sample_audio: Path, output_dir: Path):
        task = Task(input_file=sample_audio, output_format="srt")
        result = task.create_output_structure(output_dir)
        assert result.final_path.name == "final.srt"

    def test_creates_report_path(self, sample_audio: Path, output_dir: Path):
        task = Task(input_file=sample_audio)
        result = task.create_output_structure(output_dir)
        assert result.report_path.name == "report.md"

    def test_creates_debug_path(self, sample_audio: Path, output_dir: Path):
        task = Task(input_file=sample_audio)
        result = task.create_output_structure(output_dir)
        assert result.debug_path.name == "debug.json"


# ── TaskResult ───────────────────────────────────────────────


class TestTaskResult:
    """Test TaskResult structure."""

    def test_result_has_paths(self, sample_audio: Path, output_dir: Path):
        task = Task(input_file=sample_audio)
        result = task.create_output_structure(output_dir)
        assert hasattr(result, "final_path")
        assert hasattr(result, "report_path")
        assert hasattr(result, "debug_path")

    def test_result_has_quality_score(self, sample_audio: Path, output_dir: Path):
        task = Task(input_file=sample_audio)
        result = task.create_output_structure(output_dir)
        assert hasattr(result, "quality_score")

    def test_result_has_timings(self, sample_audio: Path, output_dir: Path):
        task = Task(input_file=sample_audio)
        result = task.create_output_structure(output_dir)
        assert hasattr(result, "timings")
