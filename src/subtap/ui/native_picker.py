"""Stable non-visual access to the macOS file picker."""

from __future__ import annotations

from pathlib import Path
import subprocess


def _run_picker(script: str) -> Path | None:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        selected = result.stdout.strip()
        return Path(selected) if selected else None
    if "(-128)" in result.stderr or "User canceled" in result.stderr:
        return None
    raise RuntimeError(result.stderr.strip() or "系统文件选择器启动失败")


def choose_file(prompt: str) -> Path | None:
    escaped = prompt.replace("\\", "\\\\").replace('"', '\\"')
    return _run_picker(f'POSIX path of (choose file with prompt "{escaped}")')


def choose_folder(prompt: str) -> Path | None:
    escaped = prompt.replace("\\", "\\\\").replace('"', '\\"')
    return _run_picker(f'POSIX path of (choose folder with prompt "{escaped}")')
