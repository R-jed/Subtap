"""Tests for batch progress display."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subtap.batch_progress import (
    format_progress_line,
    truncate_filename,
    format_progress_summary,
    JsonProgressWriter,
)


class TestFormatProgressLine:
    """Test progress line formatting."""

    def test_pending_item(self):
        line = format_progress_line("video.mp4", "pending", 0, 0)
        assert "○" in line
        assert "video.mp4" in line
        assert "pending" in line

    def test_running_item(self):
        line = format_progress_line("video.mp4", "running", 45, 0)
        assert "⏳" in line
        assert "45%" in line

    def test_succeeded_item(self):
        line = format_progress_line("video.mp4", "succeeded", 100, 12.3)
        assert "✓" in line
        assert "12.3s" in line

    def test_failed_item(self):
        line = format_progress_line("video.mp4", "failed", 0, 0)
        assert "✗" in line

    def test_interrupted_item(self):
        line = format_progress_line("video.mp4", "interrupted", 0, 0)
        assert "⊘" in line


class TestTruncateFilename:
    """Test filename truncation."""

    def test_short_name(self):
        name = truncate_filename("video.mp4", 40)
        assert name == "video.mp4"

    def test_long_name(self):
        name = truncate_filename("very_long_video_name_that_exceeds_limit.mp4", 40)
        assert len(name) <= 40
        assert name.endswith("...")


class TestFormatProgressSummary:
    """Test progress summary formatting."""

    def test_basic_summary(self):
        summary = format_progress_summary(3, 1, 1, 1)
        assert "✓ 1" in summary
        assert "✗ 1" in summary
        assert "⊘ 1" in summary

    def test_all_succeeded(self):
        summary = format_progress_summary(3, 3, 0, 0)
        assert "✓ 3" in summary
        assert "✗" not in summary
        assert "⊘" not in summary


class TestJsonProgressWriter:
    """Test JSON progress writer."""

    def test_write_start(self, tmp_path):
        output_file = tmp_path / "output.jsonl"
        with output_file.open("w") as f:
            writer = JsonProgressWriter(f)
            writer.write_start(3, "fast")

        lines = output_file.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["type"] == "start"
        assert data["total"] == 3
        assert data["mode"] == "fast"

    def test_write_item_complete(self, tmp_path):
        output_file = tmp_path / "output.jsonl"
        with output_file.open("w") as f:
            writer = JsonProgressWriter(f)
            writer.write_item_complete(1, "video.mp4", "succeeded", 12.3)

        lines = output_file.read_text().strip().split("\n")
        data = json.loads(lines[0])
        assert data["type"] == "item_complete"
        assert data["status"] == "succeeded"
        assert data["duration"] == 12.3

    def test_write_complete(self, tmp_path):
        output_file = tmp_path / "output.jsonl"
        with output_file.open("w") as f:
            writer = JsonProgressWriter(f)
            writer.write_complete(True, 3, 3, 0, 0, 30.5)

        lines = output_file.read_text().strip().split("\n")
        data = json.loads(lines[0])
        assert data["type"] == "complete"
        assert data["ok"] is True
        assert data["succeeded"] == 3
        assert data["duration"] == 30.5
