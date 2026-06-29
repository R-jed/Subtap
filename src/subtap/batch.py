"""Batch task helpers for user-visible manifests — v2 format."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"


PIPELINE_STAGES = ["prepare", "chunk", "asr", "clean", "segment", "align", "export"]


@dataclass
class StageInfo:
    status: StageStatus = StageStatus.PENDING
    duration: float = 0.0
    error: str = ""
    reason: str = ""
    progress: int = 0
    chunks: int = 0
    current_chunk: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"status": self.status.value}
        if self.duration > 0:
            d["duration"] = round(self.duration, 2)
        if self.error:
            d["error"] = self.error
        if self.reason:
            d["reason"] = self.reason
        if self.progress > 0 and self.status == StageStatus.RUNNING:
            d["progress"] = self.progress
        if self.chunks > 0:
            d["chunks"] = self.chunks
        if self.current_chunk > 0 and self.status == StageStatus.RUNNING:
            d["current_chunk"] = self.current_chunk
        return d


@dataclass
class ItemManifest:
    input_path: str
    output_dir: str
    status: ItemStatus = ItemStatus.PENDING
    stages: dict[str, StageInfo] = field(default_factory=lambda: {
        s: StageInfo() for s in PIPELINE_STAGES
    })
    duration: float = 0.0
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_dir": self.output_dir,
            "status": self.status.value,
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "duration": round(self.duration, 2),
            "error": self.error,
            "meta": self.meta,
        }


@dataclass
class ManifestV2:
    version: int = 2
    ok: bool = True
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    interrupted: int = 0
    output_dir: str = ""
    mode: str = "fast"
    params: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""
    duration: float = 0.0
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "ok": self.ok,
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "interrupted": self.interrupted,
            "output_dir": self.output_dir,
            "mode": self.mode,
            "params": self.params,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "duration": round(self.duration, 2),
            "items": self.items,
        }


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
    item = ItemManifest(
        input_path=str(path),
        output_dir=str(item_output_dir),
    )
    return item.to_dict()


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

    manifest = ManifestV2(
        ok=all(i.get("status") == "succeeded" for i in items),
        total=total,
        succeeded=succeeded,
        failed=failed,
        interrupted=interrupted,
        output_dir=str(output_dir),
        mode=mode,
        params=params or {},
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        items=items,
    )
    return manifest.to_dict()


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    """Write manifest JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to temp file, then rename
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
        # Clean up temp file on error
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
    return [
        item for item in items
        if item.get("status") != "succeeded"
    ]


def get_failed_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Get items that failed."""
    return [
        item for item in items
        if item.get("status") == "failed"
    ]


