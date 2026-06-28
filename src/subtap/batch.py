"""Batch task helpers for user-visible manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_files(value: str) -> list[Path]:
    """Parse comma-separated file paths."""
    return [Path(item.strip()) for item in value.split(",") if item.strip()]


def make_item(path: Path, output_dir: Path) -> dict[str, Any]:
    """Create a manifest item for one input file."""
    item_output_dir = output_dir / path.stem
    return {
        "input_path": str(path),
        "output_dir": str(item_output_dir),
        "status": "pending",
        "ok": False,
        "error": "",
        "suggestion": "",
        "meta": {},
    }


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    """Write manifest JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_manifest(
    output_dir: Path, mode: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build final batch manifest."""
    return {
        "ok": all(item["status"] == "succeeded" for item in items),
        "output_dir": str(output_dir),
        "manifest_path": str(output_dir / "manifest.json"),
        "mode": mode,
        "items": items,
    }
