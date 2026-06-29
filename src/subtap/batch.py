"""Batch task helpers for user-visible manifests — v2 format."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PIPELINE_STAGES = ["prepare", "chunk", "asr", "clean", "segment", "align", "export"]


def parse_files(value: str) -> list[Path]:
    """Parse comma-separated file paths."""
    return [Path(item.strip()) for item in value.split(",") if item.strip()]


def _make_output_dir_name(path: Path) -> str:
    """Create unique output directory name, handling filename conflicts."""
    stem = path.stem
    suffix = path.suffix.lstrip(".")
    if suffix:
        return f"{stem}_{suffix}"
    return stem


def make_item(path: Path, output_dir: Path) -> dict[str, Any]:
    """Create a manifest item for one input file."""
    item_output_dir = output_dir / _make_output_dir_name(path)
    return {
        "input_path": str(path),
        "output_dir": str(item_output_dir),
        "status": "pending",
        "stages": {s: {"status": "pending"} for s in PIPELINE_STAGES},
        "duration": 0.0,
        "error": "",
        "meta": {},
    }


def build_manifest(
    output_dir: Path,
    mode: str,
    items: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build final batch manifest.

    Args:
        created_at: 首次创建时间，后续调用应传入原始值以保留任务真正开始时间
    """
    total = len(items)
    succeeded = sum(1 for i in items if i.get("status") == "succeeded")
    failed = sum(1 for i in items if i.get("status") == "failed")
    interrupted = sum(1 for i in items if i.get("status") == "interrupted")

    return {
        "version": 2,
        "ok": all(i.get("status") == "succeeded" for i in items),
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "interrupted": interrupted,
        "output_dir": str(output_dir),
        "mode": mode,
        "params": params or {},
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "completed_at": "",
        "duration": 0.0,
        "items": items,
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    """Write manifest JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".manifest_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_manifest(path: Path) -> dict[str, Any]:
    """Load manifest JSON with version validation."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 2:
        raise ValueError(
            f"不支持的 manifest 版本：{data.get('version')}，需要 v2"
        )
    return data


def get_pending_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Get items that are not succeeded (failed, interrupted, pending)."""
    return [item for item in items if item.get("status") != "succeeded"]


def get_failed_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Get items that failed."""
    return [item for item in items if item.get("status") == "failed"]
