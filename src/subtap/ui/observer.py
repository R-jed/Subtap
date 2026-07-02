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


def _make_observer_dashboard(log_path: Path, process, refresh_interval: float = 1.0):
    """Create ObserverDashboard instance (lazy import of textual)."""
    from textual.app import App
    from textual.widgets import Footer, Header, Static

    class ObserverDashboard(App):
        """Textual 观察者：只读 run.log.jsonl，不执行 pipeline。"""

        def compose(self):
            yield Header()
            yield Static(self.build_status_text(), id="status")
            yield Footer()

        async def on_mount(self) -> None:
            self.set_interval(refresh_interval, self.refresh_from_log)
            self.refresh_from_log()

        def build_status_text(self) -> str:
            state = summarize_event_log(log_path)
            return (
                "Subtap 观察者进程\n"
                f"当前阶段：{state['stage']}\n"
                f"进度：{state['progress']}%\n"
                f"当前 Chunk：{state['chunk_id']}\n"
                f"当前模型：{state['model']}\n"
                f"ASR 草稿：{state['asr_drafts']}  已对齐：{state['aligned']}\n"
                "隐私：观察者只读取本地日志，不接触音频和模型推理"
            )

        def refresh_from_log(self) -> None:
            try:
                self.query_one("#status", Static).update(self.build_status_text())
            except Exception:
                return
            if process.poll() is not None:
                self.exit()

    return ObserverDashboard()
