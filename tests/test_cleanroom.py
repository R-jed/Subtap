"""Tests for engine/cleanroom.py — workspace hygiene checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subtap.engine.cleanroom import Cleanroom


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a mock workspace directory with standard structure."""
    (tmp_path / "audio").mkdir()
    (tmp_path / "chunks").mkdir()
    (tmp_path / "asr").mkdir()
    (tmp_path / "cleaned").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "output").mkdir()
    return tmp_path


@pytest.fixture
def cleanroom(workspace: Path) -> Cleanroom:
    return Cleanroom(workspace)


# ── check_workspace ──────────────────────────────────────────


class TestCheckWorkspace:
    """check_workspace returns a status report."""

    def test_clean_workspace_returns_clean_status(self, cleanroom: Cleanroom):
        result = cleanroom.check_workspace()
        assert result["is_clean"] is True
        assert result["issues"] == []

    def test_detects_temp_cache_files(self, workspace: Path, cleanroom: Cleanroom):
        # Create temp/cache files
        (workspace / "chunks" / "chunk_0000.wav").write_bytes(b"\x00" * 100)
        (workspace / ".DS_Store").touch()
        (workspace / "thumbs.db").touch()

        result = cleanroom.check_workspace()
        assert result["is_clean"] is False
        assert len(result["issues"]) >= 2

    def test_detects_stale_event_log(self, workspace: Path, cleanroom: Cleanroom):
        # Create a stale event log with invalid JSON
        log_path = workspace / "logs" / "event.log.jsonl"
        log_path.write_text("not valid json\n")

        result = cleanroom.check_workspace()
        assert result["is_clean"] is False
        assert any("event.log.jsonl" in issue for issue in result["issues"])

    def test_preserves_output_srt(self, workspace: Path, cleanroom: Cleanroom):
        # Output SRT files must NOT be flagged
        (workspace / "output" / "test.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        (workspace / "output" / "test.json").write_text("{}")

        result = cleanroom.check_workspace()
        assert result["is_clean"] is True

    def test_preserves_aligned_jsonl(self, workspace: Path, cleanroom: Cleanroom):
        # aligned.jsonl in root is user data, not temp
        (workspace / "aligned.jsonl").write_text("{}\n")

        result = cleanroom.check_workspace()
        assert result["is_clean"] is True


# ── clean_workspace ──────────────────────────────────────────


class TestCleanWorkspace:
    """clean_workspace removes temp files but preserves user output."""

    def test_removes_temp_files(self, workspace: Path, cleanroom: Cleanroom):
        temp_file = workspace / "chunks" / "chunk_0000.wav"
        temp_file.write_bytes(b"\x00" * 100)
        ds_store = workspace / ".DS_Store"
        ds_store.touch()

        report = cleanroom.clean_workspace()

        assert not temp_file.exists()
        assert not ds_store.exists()
        assert report["cleaned_count"] >= 2

    def test_does_not_remove_output_srt(self, workspace: Path, cleanroom: Cleanroom):
        srt_path = workspace / "output" / "test.srt"
        srt_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

        cleanroom.clean_workspace()

        assert srt_path.exists()

    def test_does_not_remove_aligned_jsonl(self, workspace: Path, cleanroom: Cleanroom):
        aligned = workspace / "aligned.jsonl"
        aligned.write_text("{}\n")

        cleanroom.clean_workspace()

        assert aligned.exists()

    def test_fixes_corrupt_event_log(self, workspace: Path, cleanroom: Cleanroom):
        log_path = workspace / "logs" / "event.log.jsonl"
        log_path.write_text("not valid json\nbad line\n")

        cleanroom.clean_workspace()

        # Should be cleaned (removed or fixed)
        assert not log_path.exists() or log_path.read_text().strip() == ""

    def test_returns_cleaned_count(self, workspace: Path, cleanroom: Cleanroom):
        (workspace / ".DS_Store").touch()
        (workspace / "thumbs.db").touch()

        report = cleanroom.clean_workspace()
        assert report["cleaned_count"] == 2

    def test_returns_report_dict(self, workspace: Path, cleanroom: Cleanroom):
        report = cleanroom.clean_workspace()
        assert "cleaned_count" in report
        assert "issues" in report
        assert "is_clean" in report


# ── check_model_status ───────────────────────────────────────


class TestCheckModelStatus:
    """check_model_status reports model availability."""

    def test_returns_model_status_dict(self, cleanroom: Cleanroom):
        result = cleanroom.check_model_status()
        assert isinstance(result, dict)
        assert "models" in result

    def test_reports_missing_models(self, cleanroom: Cleanroom):
        result = cleanroom.check_model_status()
        # Models directory may not exist in test env
        for model in result["models"]:
            assert "name" in model
            assert "installed" in model
