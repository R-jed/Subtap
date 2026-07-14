"""Run log — human-readable execution record for debugging and review.

Usage::

    with RunLog(work_dir) as log:
        log.system(python="3.12.0", mlx="0.26.1", ...)
        log.input(path, size_bytes, fmt, duration_sec)
        log.config_snapshot(config_dict)
        log.hotwords(...)
        log.stage("vad", "success", duration_sec=1.2, details="...")
        try:
            ...
            log.finalize(True, total_duration_sec=...)
        except Exception:
            log.finalize(False, error=traceback.format_exc())
            raise
"""

from __future__ import annotations

import sys
import platform
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class StageRecord:
    name: str
    status: str  # "success" | "fail" | "skipped"
    duration_sec: float
    details: str = ""


@dataclass
class RunLog:
    """Collects pipeline execution info and writes human-readable log.

    Each run overwrites the previous log (debugging purpose, not archival).
    """

    work_dir: Path
    log_path: Path | None = None  # If None, defaults to work_dir / "run.log"
    _system_info: dict[str, str] = field(default_factory=dict)
    _input_info: dict[str, Any] = field(default_factory=dict)
    _config: dict[str, Any] = field(default_factory=dict)
    _hotwords: dict[str, Any] = field(default_factory=dict)
    _stages: list[StageRecord] = field(default_factory=list)
    _start_time: datetime | None = None
    _finalized: bool = False
    _final_status: str | None = None
    _final_duration: float | None = None
    _final_error: str | None = None
    _final_output: str | None = None

    def __enter__(self) -> RunLog:
        self._start_time = datetime.now().astimezone()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self._finalized:
            if exc_type is not None:
                self.finalize(False, error=traceback.format_exc())
            else:
                self.finalize(True)

    # ── System ──────────────────────────────────────────────────

    def system(self, python: str = "", mlx: str = "", ffmpeg: str = "") -> None:
        self._system_info = {
            "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "python": python or sys.version.split()[0],
            "mlx": mlx,
            "ffmpeg": ffmpeg,
        }

    # ── Input ───────────────────────────────────────────────────

    def input(
        self,
        path: Path,
        size_bytes: int,
        format: str,
        duration_sec: float | None = None,
        sample_rate: int | None = None,
        channels: int | None = None,
    ) -> None:
        self._input_info = {
            "path": str(path),
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "format": format,
            "duration_sec": duration_sec,
            "sample_rate": sample_rate,
            "channels": channels,
        }

    # ── Config ──────────────────────────────────────────────────

    def config_snapshot(self, config: dict[str, Any]) -> None:
        self._config = config

    # ── Hotwords ────────────────────────────────────────────────

    def hotwords(
        self,
        path: Path | None = None,
        count: int | None = None,
        loaded: bool = False,
    ) -> None:
        self._hotwords = {
            "path": str(path) if path else None,
            "count": count,
            "loaded": loaded,
        }

    # ── Stages ──────────────────────────────────────────────────

    def stage(
        self,
        name: str,
        status: str,
        duration_sec: float = 0.0,
        details: str = "",
    ) -> None:
        self._stages.append(
            StageRecord(
                name=name, status=status, duration_sec=duration_sec, details=details
            )
        )

    # ── Finalize ────────────────────────────────────────────────

    def finalize(
        self,
        success: bool,
        total_duration_sec: float | None = None,
        error: str | None = None,
        output_path: str | None = None,
    ) -> None:
        self._finalized = True
        self._final_status = "success" if success else "fail"
        self._final_duration = total_duration_sec
        self._final_error = error
        self._final_output = output_path
        self._write()

    # ── Rendering ───────────────────────────────────────────────

    def render(self) -> str:
        lines: list[str] = []
        sep = "─" * 60
        thick = "═" * 60

        # Header
        start_str = (
            self._start_time.strftime("%Y-%m-%d %H:%M:%S")
            if self._start_time
            else "unknown"
        )
        lines.append(thick)
        lines.append(f"  Subtap Pipeline Run Log — {start_str}")
        lines.append(thick)

        # Source file (prominent display)
        if self._input_info.get("path"):
            lines.append("")
            lines.append(f"  ▶ 源文件: {self._input_info['path']}")
            if self._input_info.get("size_mb") is not None:
                lines.append(
                    f"    大小: {self._input_info['size_mb']} MB  格式: {self._input_info.get('format', 'unknown')}"
                )
                if self._input_info.get("duration_sec"):
                    lines.append(
                        f"    时长: {self._input_info['duration_sec']:.1f}s  采样率: {self._input_info.get('sample_rate', 'N/A')}Hz  声道: {self._input_info.get('channels', 'N/A')}"
                    )

        # System
        if self._system_info:
            lines.append("")
            lines.append("  【系统环境】")
            for k, v in self._system_info.items():
                if v:
                    lines.append(f"    {k:12s} : {v}")

        # Input
        if self._input_info:
            lines.append("")
            lines.append("  【输入文件】")
            for k, v in self._input_info.items():
                if v is not None:
                    lines.append(f"    {k:12s} : {v}")

        # Config
        if self._config:
            lines.append("")
            lines.append("  【运行配置】")
            for k, v in self._config.items():
                lines.append(f"    {k:20s} : {v}")

        # Hotwords
        if self._hotwords.get("path") or self._hotwords.get("loaded"):
            lines.append("")
            lines.append("  【热词表】")
            p = self._hotwords.get("path")
            if p:
                lines.append(f"    {'path':12s} : {p}")
            c = self._hotwords.get("count")
            if c is not None:
                lines.append(f"    {'entries':12s} : {c}")
            loaded = self._hotwords.get("loaded", False)
            lines.append(f"    {'loaded':12s} : {'是' if loaded else '否'}")

        # Stages
        if self._stages:
            lines.append("")
            lines.append("  【阶段执行】")
            lines.append(f"    {'阶段':<20s} {'状态':>6s} {'耗时':>10s}  {'详情'}")
            lines.append(f"    {'─' * 20} {'─' * 6} {'─' * 10}  {'─' * 20}")
            for s in self._stages:
                status_icon = {"success": "✅", "fail": "❌", "skipped": "⏭️"}.get(
                    s.status, s.status
                )
                dur = f"{s.duration_sec:.1f}s" if s.duration_sec else ""
                det = s.details[:40] if s.details else ""
                lines.append(f"    {s.name:<20s} {status_icon:>6s} {dur:>10s}  {det}")

        # Final
        lines.append("")
        lines.append(sep)
        status_str = self._final_status or "unknown"
        if status_str == "success":
            lines.append("  ✅ Pipeline 完成")
        else:
            lines.append("  ❌ Pipeline 失败")

        if self._final_duration is not None:
            lines.append(f"  总耗时: {self._final_duration:.1f}s")
        if self._final_output:
            lines.append(f"  输出: {self._final_output}")
        if self._final_error:
            lines.append("")
            lines.append("  【错误详情】")
            for line in self._final_error.splitlines():
                lines.append(f"    {line}")
        lines.append(thick)

        return "\n".join(lines) + "\n"

    # ── Write ───────────────────────────────────────────────────

    def _write(self) -> None:
        if self.log_path:
            target = self.log_path
        else:
            ts = (
                self._start_time.strftime("%Y%m%d_%H%M%S")
                if self._start_time
                else "unknown"
            )
            target = self.work_dir / f"run_{ts}.log"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(), encoding="utf-8")
        # 同时写一份 latest 符号链接方便快速查看
        latest = self.work_dir / "run_latest.log"
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(target.name)
