"""Tests for RunLog — human-readable pipeline execution record."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from subtap.metrics.run_log import RunLog


class TestRunLogDataCollection:
    """RunLog correctly collects and renders all sections."""

    def test_system_info_rendered(self, tmp_path: Path) -> None:
        log = RunLog(work_dir=tmp_path)
        log.system(python="3.12.0", mlx="0.26.1", ffmpeg="7.1")
        output = log.render()
        assert "系统环境" in output
        assert "3.12.0" in output
        assert "0.26.1" in output

    def test_input_info_rendered(self, tmp_path: Path) -> None:
        log = RunLog(work_dir=tmp_path)
        log.input(
            path=Path("/tmp/test.mp3"),
            size_bytes=1048576,
            format="mp3",
            duration_sec=120.5,
        )
        output = log.render()
        assert "输入文件" in output
        assert "test.mp3" in output
        assert "1.0" in output  # 1MB

    def test_config_snapshot_rendered(self, tmp_path: Path) -> None:
        log = RunLog(work_dir=tmp_path)
        log.config_snapshot({"mode": "fast", "enhance": "local"})
        output = log.render()
        assert "运行配置" in output
        assert "fast" in output

    def test_stages_rendered(self, tmp_path: Path) -> None:
        log = RunLog(work_dir=tmp_path)
        log.stage("vad", "success", duration_sec=1.2, details="3 chunks")
        log.stage("asr", "fail", duration_sec=5.0, details="model not found")
        output = log.render()
        assert "阶段执行" in output
        assert "vad" in output
        assert "asr" in output

    def test_finalize_success(self, tmp_path: Path) -> None:
        log = RunLog(work_dir=tmp_path)
        log.system()
        log.finalize(True, total_duration_sec=42.5, output_path="/tmp/final.srt")
        output = log.render()
        assert "Pipeline 完成" in output
        assert "42.5" in output
        assert "/tmp/final.srt" in output

    def test_finalize_failure_with_error(self, tmp_path: Path) -> None:
        log = RunLog(work_dir=tmp_path)
        log.system()
        log.finalize(False, error="Traceback:\n  FileNotFoundError")
        output = log.render()
        assert "Pipeline 失败" in output
        assert "FileNotFoundError" in output

    def test_hotwords_rendered(self, tmp_path: Path) -> None:
        log = RunLog(work_dir=tmp_path)
        log.hotwords(
            path=Path("~/.subtap/glossary/hotwords_zh.txt"), count=15, loaded=True
        )
        output = log.render()
        assert "热词表" in output
        assert "15" in output


class TestRunLogContextManager:
    """RunLog works as a context manager."""

    def _find_log(self, tmp_path: Path) -> Path:
        """Find the generated run log file (timestamped name)."""
        logs = sorted(tmp_path.glob("run_*.log"))
        assert logs, f"No run_*.log found in {tmp_path}"
        return logs[-1]

    def test_context_manager_writes_on_exit(self, tmp_path: Path) -> None:
        with RunLog(work_dir=tmp_path) as log:
            log.system(python="3.12.0")
        log_path = self._find_log(tmp_path)
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "3.12.0" in content
        # latest symlink should exist
        assert (tmp_path / "run_latest.log").exists()

    def test_context_manager_captures_exception(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            with RunLog(work_dir=tmp_path) as log:
                log.system()
                raise ValueError("test error")
        log_path = self._find_log(tmp_path)
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "Pipeline 失败" in content
        assert "ValueError" in content

    def test_overwrite_on_each_run(self, tmp_path: Path) -> None:
        with RunLog(work_dir=tmp_path) as log:
            log.system(python="first")
        with RunLog(work_dir=tmp_path) as log:
            log.system(python="second")
        # Each run creates a new file, check latest symlink
        latest = tmp_path / "run_latest.log"
        assert latest.exists()
        content = latest.read_text(encoding="utf-8")
        assert "second" in content


class TestRunLogE2E:
    """End-to-end: full lifecycle renders correct log."""

    def test_full_lifecycle(self, tmp_path: Path) -> None:
        with RunLog(work_dir=tmp_path) as log:
            log.system(python="3.12.0", mlx="0.26.1")
            log.input(
                path=Path("/audio/test.mp3"),
                size_bytes=5_000_000,
                format="mp3",
                duration_sec=300,
            )
            log.config_snapshot({"mode": "fast", "enhance": "local"})
            log.hotwords(
                path=Path("~/.subtap/glossary/hotwords_zh.txt"), count=10, loaded=True
            )
            time.sleep(0.01)
            log.stage("vad", "success", duration_sec=0.5, details="5 chunks")
            log.stage("asr", "success", duration_sec=12.3, details="5/5 chunks")
            log.stage("alignment", "success", duration_sec=8.1)
            log.finalize(True, total_duration_sec=21.0, output_path="/out/final.srt")
        latest = tmp_path / "run_latest.log"
        content = latest.read_text(encoding="utf-8")
        assert "Pipeline 完成" in content
        assert "test.mp3" in content
        assert "热词表" in content
        assert "vad" in content
        assert "asr" in content
        assert "alignment" in content
        assert "21.0" in content
