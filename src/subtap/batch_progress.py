"""Batch progress display — terminal and JSON output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

import typer


def truncate_filename(name: str, max_len: int = 40) -> str:
    """Truncate filename if too long."""
    if len(name) <= max_len:
        return name
    return name[: max_len - 3] + "..."


def format_progress_line(
    filename: str,
    status: str,
    progress: int,
    duration: float,
    stage: str = "",
) -> str:
    """Format a single progress line."""
    name = truncate_filename(filename)

    if status == "succeeded":
        icon = "✓"
        detail = f"{duration:.1f}s"
    elif status == "failed":
        icon = "✗"
        detail = "failed"
    elif status == "running":
        icon = "⏳"
        if stage:
            detail = f"{stage} {progress}%"
        else:
            detail = f"{progress}%"
    elif status == "interrupted":
        icon = "⊘"
        detail = "interrupted"
    else:
        icon = "○"
        detail = "pending"

    return f"  {icon} {name} — {detail}"


def format_progress_summary(
    total: int,
    succeeded: int,
    failed: int,
    interrupted: int,
) -> str:
    """Format progress summary line."""
    parts = []
    if succeeded:
        parts.append(f"✓ {succeeded}")
    if failed:
        parts.append(f"✗ {failed}")
    if interrupted:
        parts.append(f"⊘ {interrupted}")
    pending = total - succeeded - failed - interrupted
    if pending:
        parts.append(f"○ {pending}")
    return f"▸ 批量转录：{total} 个文件 ({', '.join(parts)})"


def print_progress_header(total: int, mode: str) -> None:
    """Print progress header."""
    typer.echo(f"▸ 批量转录：{total} 个文件，模式：{mode}")


def print_progress_item(
    index: int,
    total: int,
    filename: str,
    status: str,
    progress: int = 0,
    duration: float = 0.0,
    stage: str = "",
) -> None:
    """Print progress for a single item."""
    line = format_progress_line(filename, status, progress, duration, stage)
    typer.echo(line)


def print_progress_footer(
    total: int,
    succeeded: int,
    failed: int,
    interrupted: int,
    duration: float,
) -> None:
    """Print progress footer summary."""
    summary = format_progress_summary(total, succeeded, failed, interrupted)
    typer.echo(f"\n{summary}")
    typer.echo(f"总耗时：{duration:.1f}s")


# JSON streaming output

class JsonProgressWriter:
    """Write progress as JSON Lines."""

    def __init__(self, output: TextIO | None = None):
        self.output = output or sys.stdout

    def write_start(self, total: int, mode: str, created_at: str = "") -> None:
        data = {
            "type": "start",
            "total": total,
            "mode": mode,
        }
        if created_at:
            data["created_at"] = created_at
        self._write(data)

    def write_item_start(self, index: int, filename: str) -> None:
        self._write({
            "type": "item_start",
            "index": index,
            "file": filename,
        })

    def write_item_progress(
        self,
        index: int,
        filename: str,
        stage: str,
        progress: int,
    ) -> None:
        self._write({
            "type": "item_progress",
            "index": index,
            "file": filename,
            "stage": stage,
            "progress": progress,
        })

    def write_item_complete(
        self,
        index: int,
        filename: str,
        status: str,
        duration: float = 0.0,
        error: str = "",
    ) -> None:
        data = {
            "type": "item_complete",
            "index": index,
            "file": filename,
            "status": status,
            "duration": round(duration, 2),
        }
        if error:
            data["error"] = error
        self._write(data)

    def write_complete(
        self,
        ok: bool,
        total: int,
        succeeded: int,
        failed: int,
        interrupted: int,
        duration: float,
    ) -> None:
        self._write({
            "type": "complete",
            "ok": ok,
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "interrupted": interrupted,
            "duration": round(duration, 2),
        })

    def _write(self, data: dict[str, Any]) -> None:
        self.output.write(json.dumps(data, ensure_ascii=False) + "\n")
        self.output.flush()
