"""Observer-process helpers for reading pipeline event logs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import subprocess
import time
from typing import Any

from subtap.engine.state import STAGE_CN

logger = logging.getLogger(__name__)
_UNSET = object()

SUBTAP_ASCII = """
█▀▀ █ █ █▀▄ ▀█▀ ▄▀█ █▀█
▄██ █▄█ █▄▀  █  █▀█ █▀▀
"""

_OBSERVED_STAGE_ORDER = [
    "prepare",
    "chunk",
    "asr",
    "clean",
    "segment",
    "align",
    "hotword",
    "learn",
    "export",
]
_OBSERVED_STAGE_CN = {
    **STAGE_CN,
    "script_match": "文稿匹配",
    "hotword": "热词替换",
    "learn": "热词学习",
    "translate": "字幕翻译",
}


def iter_event_log(log_path: Path) -> list[dict[str, Any]]:
    """Read run.log.jsonl rows that were fully written."""
    if not log_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    raw_lines = log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    for line_number, line in enumerate(raw_lines, start=1):
        if not line.strip():
            continue
        if line_number == len(raw_lines) and not line.endswith(("\n", "\r")):
            break
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid event log row {log_path}:{line_number}"
            ) from error
        if not isinstance(row, dict) or not isinstance(row.get("data", {}), dict):
            raise ValueError(f"Invalid event log row {log_path}:{line_number}")
        rows.append(row)
    return rows


def _summarize_event_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce validated event rows into the latest pipeline state."""
    state: dict[str, Any] = {
        "stage": "等待中",
        "progress": None,
        "chunk_id": None,
        "model": "未知",
        "asr_drafts": 0,
        "aligned": 0,
        "completed_stages": [],
        "item_index": None,
        "total_items": None,
        "recent_texts": [],
        "started_at": None,
        "last_event_at": None,
        "stage_progress": 0,
        "stage_order": list(_OBSERVED_STAGE_ORDER),
        "has_pipeline_plan": False,
    }
    draft_texts: list[str] = []
    aligned_texts: list[str] = []
    for row in rows:
        event_type = row.get("event_type")
        data = row.get("data") or {}
        if state["started_at"] is None:
            state["started_at"] = row.get("timestamp")
        if row.get("timestamp") is not None:
            state["last_event_at"] = row["timestamp"]
        if event_type == "pipeline_plan" and data.get("stages"):
            state["stage_order"] = list(data["stages"])
            state["has_pipeline_plan"] = True
        if "stage" in data:
            state["stage"] = data["stage"]
        if event_type == "stage_start":
            state["stage_progress"] = 0
            state["item_index"] = None
            state["total_items"] = None
        if "progress" in data:
            state["stage_progress"] = data["progress"]
        if "chunk_id" in data:
            state["chunk_id"] = data["chunk_id"]
        if "model" in data:
            state["model"] = data["model"]
        if "item_index" in data:
            state["item_index"] = data["item_index"]
        if "total_items" in data:
            state["total_items"] = data["total_items"]
        if event_type == "stage_end" and data.get("stage"):
            state["stage_progress"] = 100
            stage = data["stage"]
            if stage not in state["completed_stages"]:
                state["completed_stages"].append(stage)
        if event_type == "asr_draft_ready":
            state["asr_drafts"] += 1
            if data.get("text"):
                draft_texts.append(data["text"])
        if event_type == "alignment_ready":
            state["aligned"] += 1
            if data.get("text"):
                aligned_texts.append(data["text"])
    stage_order = state["stage_order"]
    completed = {stage for stage in state["completed_stages"] if stage in stage_order}
    current_stage = state["stage"]
    current_fraction = (
        state["stage_progress"] / 100
        if current_stage in stage_order and current_stage not in completed
        else 0
    )
    state["progress"] = (
        round((len(completed) + current_fraction) / len(stage_order) * 100)
        if state["has_pipeline_plan"]
        else state["stage_progress"]
    )
    state["recent_texts"] = (aligned_texts or draft_texts)[-4:]
    return state


def summarize_event_log(log_path: Path) -> dict[str, Any]:
    """Build the latest observable pipeline state from run.log.jsonl."""
    return _summarize_event_rows(iter_event_log(log_path))


def build_command_deck_text(state: dict[str, Any]) -> str:
    """Format pipeline state as human-readable text for CLI output."""
    progress = state["progress"]
    progress_text = f"{progress}%" if progress is not None else "计算中"
    return (
        f"当前阶段：{state['stage']}\n"
        f"进度：{progress_text}\n"
        f"当前 Chunk：{state['chunk_id']}\n"
        f"当前模型：{state['model']}\n"
        f"ASR 草稿：{state['asr_drafts']}  已对齐：{state['aligned']}"
    )


def _make_observer_dashboard(
    log_path: Path,
    process,
    refresh_interval: float = 1.0,
    output_path: Path | None = None,
):
    """Create ObserverDashboard instance (lazy import of textual)."""
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Header, ProgressBar, RichLog, Static
    from rich.text import Text

    class CancelTaskScreen(ModalScreen[bool]):
        """Require an explicit answer before stopping the pipeline."""

        CSS = """
        CancelTaskScreen {
            align: center middle;
            background: $background 70%;
        }
        #cancel-dialog {
            width: 58;
            height: auto;
            padding: 2 3;
            border: round $error;
            background: $surface;
        }
        """
        BINDINGS = [
            ("y", "confirm", "确认停止"),
            ("n", "keep_running", "继续运行"),
            ("escape", "keep_running", "返回"),
        ]

        def compose(self) -> ComposeResult:
            with Vertical(id="cancel-dialog"):
                yield Static(
                    "[b]停止当前任务？[/b]\n\n"
                    "这会终止字幕处理；已生成的工作文件会保留。\n\n"
                    "按 Y 确认，按 N 或 Esc 返回。"
                )

        def action_confirm(self) -> None:
            self.dismiss(True)

        def action_keep_running(self) -> None:
            self.dismiss(False)

    class ObserverDashboard(App):
        """Textual 观察者：只读 run.log.jsonl，不执行 pipeline。"""

        CSS = """
        Screen {
            layout: vertical;
        }
        #task-panel {
            margin: 1 2;
            padding: 1 2;
            border: round $accent;
            height: auto;
        }
        #stage-map, #current-work, #recent, #output {
            margin-top: 1;
        }
        #details {
            margin: 0 2 1 2;
            border: round $secondary;
            height: 1fr;
            display: none;
        }
        #keys {
            dock: bottom;
            height: 1;
            padding: 0 2;
            color: #8b8b92;
            background: #111820;
        }
        """
        BINDINGS = [
            ("l", "toggle_details", "详情"),
            ("f", "open_output_directory", "输出目录"),
            ("d", "open_diagnostics", "诊断日志"),
            ("escape", "show_overview", "返回概览"),
            ("q", "quit_observer", "退出观察"),
            ("x", "cancel_task", "停止任务"),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            with Vertical(id="task-panel"):
                yield Static(self.build_status_text(), id="status")
                yield ProgressBar(total=100, show_eta=False, id="progress")
                yield Static("", id="stage-map")
                yield Static("", id="current-work")
                yield Static("", id="recent")
                yield Static("", id="output")
                yield Static("", id="action-status")
            yield RichLog(max_lines=200, auto_scroll=True, id="details")
            yield Static("", id="keys")

        async def on_mount(self) -> None:
            self.set_interval(refresh_interval, self.refresh_from_log)
            self.refresh_from_log()

        def build_status_text(
            self,
            state: dict[str, Any] | None = None,
            returncode: Any = _UNSET,
        ) -> str:
            if state is None:
                state = summarize_event_log(log_path)
            if returncode is _UNSET:
                returncode = process.poll()
            if returncode is None:
                task_status = "任务运行中"
            elif returncode == 0:
                task_status = (
                    "任务已完成"
                    if output_path is None or output_path.is_file()
                    else "任务异常：未找到字幕文件"
                )
            else:
                task_status = f"任务失败（退出码 {returncode}）"
            progress = state["progress"]
            progress_text = f"{progress}%" if progress is not None else "计算中"
            output_text = f"\n输出文件：{output_path}" if output_path else ""
            return (
                f"[b]{task_status}[/b]\n"
                f"当前阶段：{state['stage']}\n"
                f"进度：{progress_text}\n"
                f"当前 Chunk：{state['chunk_id']}\n"
                f"当前模型：{state['model']}\n"
                f"ASR 草稿：{state['asr_drafts']}  已对齐：{state['aligned']}\n"
                "隐私：观察者只读取本地日志，不接触音频和模型推理"
                f"{output_text}"
            )

        def refresh_from_log(self) -> None:
            rows = iter_event_log(log_path)
            state = _summarize_event_rows(rows)
            returncode = process.poll()
            self.query_one("#status", Static).update(
                self.build_status_text(state, returncode)
            )

            progress = state["progress"]
            bar = self.query_one("#progress", ProgressBar)
            if progress is None:
                bar.update(total=None)
            else:
                bar.update(total=100, progress=progress)

            completed = set(state["completed_stages"])
            current = state["stage"]
            stages = []
            for stage in state["stage_order"]:
                marker = "✓" if stage in completed else "▶" if stage == current else "·"
                stages.append(f"{marker} {_OBSERVED_STAGE_CN.get(stage, stage)}")
            self.query_one("#stage-map", Static).update("  ".join(stages))

            item_index = state["item_index"]
            total_items = state["total_items"]
            item_text = (
                f"当前项目：{item_index}/{total_items}"
                if item_index is not None and total_items is not None
                else f"当前 Chunk：{state['chunk_id']}"
            )
            elapsed = 0
            if state["started_at"] is not None:
                end_time = (
                    time.time()
                    if returncode is None
                    else state["last_event_at"] or state["started_at"]
                )
                elapsed = max(0, int(end_time - state["started_at"]))
            self.query_one("#current-work", Static).update(
                f"{item_text}  已用时：{elapsed // 60:02d}:{elapsed % 60:02d}"
            )

            recent = state["recent_texts"]
            recent_text = "\n".join(f"  {text}" for text in recent)
            self.query_one("#recent", Static).update(
                f"[b]最近字幕[/b]\n{recent_text or '  暂无'}"
            )
            if returncode is None:
                output_text = f"[b]输出[/b]  {output_path or '任务完成后显示'}"
            elif returncode == 0 and output_path is not None and output_path.is_file():
                output_text = (
                    f"[green]✓ 字幕已生成[/green]  {output_path}\n"
                    "F 打开输出目录  Q 返回"
                )
            elif returncode == 0 and output_path is not None:
                output_text = (
                    f"[red]未找到字幕文件[/red]  {output_path}\n"
                    "D 打开诊断日志  Q 返回"
                )
            else:
                output_text = "[red]未生成可交付字幕[/red]\nD 打开诊断日志  Q 返回"
            self.query_one("#output", Static).update(output_text)
            if returncode is None:
                keys = (
                    "L 详情   F 输出目录   D 诊断日志   Esc 返回概览   "
                    "Q 退出观察   X 停止任务"
                )
            elif returncode == 0 and output_path is not None and output_path.is_file():
                keys = "F 输出目录   Q 返回"
            else:
                keys = "D 诊断日志   Q 返回"
            self.query_one("#keys", Static).update(keys)

            details = self.query_one("#details", RichLog)
            details.clear()
            for row in rows[-50:]:
                data = row.get("data") or {}
                message = data.get("message_zh") or row.get("event_type", "未知事件")
                details.write(f"{data.get('stage', '-'):>8}  {message}")

        def action_toggle_details(self) -> None:
            details = self.query_one("#details", RichLog)
            details.display = not details.display

        def _open_path(self, target: Path, label: str) -> None:
            status = self.query_one("#action-status", Static)
            try:
                result = subprocess.run(
                    ["open", str(target)],
                    capture_output=True,
                    text=True,
                )
            except OSError as error:
                logger.exception("打开%s失败：%s", label, target)
                status.update(f"打开{label}失败：{error}")
                return
            if result.returncode:
                detail = result.stderr.strip() or f"退出码 {result.returncode}"
                logger.error("打开%s失败：%s", label, detail)
                status.update(Text(f"打开{label}失败：{detail}"))
            else:
                status.update(f"已打开{label}。")

        def _open_completed_result(self, target: Path, label: str) -> None:
            status = self.query_one("#action-status", Static)
            if process.poll() is None:
                status.update("任务完成后才能打开结果。")
                return
            if (
                process.returncode != 0
                or output_path is None
                or not output_path.is_file()
            ):
                status.update("没有可打开的字幕结果。")
                return
            self._open_path(target, label)

        def action_open_output_directory(self) -> None:
            if output_path is None:
                self.query_one("#action-status", Static).update(
                    "没有可打开的字幕结果。"
                )
                return
            self._open_completed_result(output_path.parent, "输出目录")

        def action_open_diagnostics(self) -> None:
            status = self.query_one("#action-status", Static)
            diagnostic_path = log_path.with_name("run_latest.log")
            if process.poll() is None:
                status.update("任务结束后才能打开诊断日志。")
            elif not diagnostic_path.is_file():
                status.update(f"未找到诊断日志：{diagnostic_path}")
            else:
                self._open_path(diagnostic_path, "诊断日志")

        def action_show_overview(self) -> None:
            self.query_one("#details", RichLog).display = False

        def action_quit_observer(self) -> None:
            self.exit("quit")

        def action_cancel_task(self) -> None:
            if process.poll() is None:
                self.push_screen(CancelTaskScreen(), self._finish_cancel)

        def _finish_cancel(self, confirmed: bool | None) -> None:
            if confirmed and process.poll() is None:
                self.exit("interrupt")
            elif confirmed:
                self.refresh_from_log()

    return ObserverDashboard()
