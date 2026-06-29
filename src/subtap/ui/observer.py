"""Observer-process helpers for reading pipeline event logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def iter_event_log(log_path: Path) -> list[dict[str, Any]]:
    """Read run.log.jsonl rows that were fully written."""
    if not log_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize_event_log(log_path: Path) -> dict[str, Any]:
    """Build the latest observable pipeline state from run.log.jsonl."""
    state: dict[str, Any] = {
        "stage": "等待中",
        "progress": 0,
        "chunk_id": None,
        "model": "未知",
        "asr_drafts": 0,
        "aligned": 0,
    }
    for row in iter_event_log(log_path):
        event_type = row.get("event_type")
        data = row.get("data") or {}
        if "stage" in data:
            state["stage"] = data["stage"]
        if "progress" in data:
            state["progress"] = data["progress"]
        if "chunk_id" in data:
            state["chunk_id"] = data["chunk_id"]
        if "model" in data:
            state["model"] = data["model"]
        if event_type == "asr_draft_ready":
            state["asr_drafts"] += 1
        if event_type == "alignment_ready":
            state["aligned"] += 1
    return state
