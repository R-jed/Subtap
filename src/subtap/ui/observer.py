"""Observer-process helpers for reading pipeline event logs."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class TaskPresentation:
    """Stable task view consumed by live and historical observer screens."""

    status: str
    stage: str
    progress: int | None
    model: str
    counts: str
    current_work: str
    stage_lines: tuple[str, ...]
    recent_texts: tuple[str, ...]
    output_text: str


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


def build_task_presentation(
    state: dict[str, Any],
    *,
    returncode: int | None | object = _UNSET,
    output_path: Path | None = None,
    now: float | None = None,
) -> TaskPresentation:
    """Translate reducer state into one shared task presentation."""
    if returncode is _UNSET:
        status = "任务记录"
    elif returncode is None:
        status = "任务运行中"
    elif returncode == 0:
        status = (
            "任务已完成"
            if output_path is None or output_path.is_file()
            else "任务异常：未找到字幕文件"
        )
    else:
        status = f"任务失败（退出码 {returncode}）"

    completed = set(state["completed_stages"])
    current = state["stage"]
    stage_lines = tuple(
        f"{'✓' if stage in completed else '▶' if stage == current else '·'} "
        f"{_OBSERVED_STAGE_CN.get(stage, stage)}"
        for stage in state["stage_order"]
    )
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
            now if returncode is None and now is not None else state["last_event_at"]
        )
        if end_time is None:
            end_time = state["started_at"]
        elapsed = max(0, int(end_time - state["started_at"]))
    current_work = f"{item_text}  已用时：{elapsed // 60:02d}:{elapsed % 60:02d}"

    if returncode is _UNSET:
        output_text = f"[b]输出[/b]  {output_path or '未记录'}"
    elif returncode is None:
        output_text = f"[b]输出[/b]  {output_path or '任务完成后显示'}"
    elif returncode == 0 and output_path is not None and output_path.is_file():
        output_text = f"[green]✓ 字幕已生成[/green]\n{output_path}"
    elif returncode == 0 and output_path is not None:
        output_text = f"[red]未找到字幕文件[/red]\n{output_path}"
    else:
        output_text = "[red]未生成可交付字幕[/red]"

    return TaskPresentation(
        status=status,
        stage=str(state["stage"]),
        progress=state["progress"],
        model=str(state["model"]),
        counts=f"ASR 草稿：{state['asr_drafts']}  已对齐：{state['aligned']}",
        current_work=current_work,
        stage_lines=stage_lines,
        recent_texts=tuple(state["recent_texts"]),
        output_text=output_text,
    )


def build_task_status_text(presentation: TaskPresentation) -> str:
    progress_text = (
        f"{presentation.progress}%" if presentation.progress is not None else "计算中"
    )
    return (
        f"[b]{presentation.status}[/b]\n"
        f"当前阶段：{presentation.stage}\n"
        f"进度：{progress_text}\n"
        f"当前模型：{presentation.model}\n"
        f"{presentation.counts}\n"
        f"{presentation.current_work}\n"
        "隐私：观察者只读取本地日志，不接触音频和模型推理\n"
        f"{presentation.output_text}"
    )


def build_command_deck_text(state: dict[str, Any]) -> str:
    """Format pipeline state as human-readable text for CLI output."""
    return build_task_status_text(build_task_presentation(state))


def _make_observer_dashboard(
    log_path: Path,
    process,
    refresh_interval: float = 1.0,
    output_path: Path | None = None,
):
    """Create ObserverDashboard instance (lazy import of textual)."""
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Grid, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Footer, ProgressBar, RichLog, Static
    from rich.text import Text
    from subtap.ui.theme import CALM_WORKBENCH_BREAKPOINTS, CALM_WORKBENCH_CSS

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

        HORIZONTAL_BREAKPOINTS = CALM_WORKBENCH_BREAKPOINTS
        CSS = CALM_WORKBENCH_CSS + """
        Screen {
            layout: vertical;
            align: center top;
        }
        #task-panel {
            width: 100%;
            max-width: 104;
            height: 1fr;
            padding: 1 2 0 2;
        }
        #status {
            height: auto;
            padding-bottom: 1;
        }
        #progress { margin-bottom: 1; }
        #task-layout {
            grid-size: 2 1;
            grid-columns: 2fr 3fr;
            grid-rows: auto;
            grid-gutter: 1 2;
            height: auto;
        }
        #pipeline-pane, #activity-pane {
            height: auto;
            padding: 1 2;
            background: $surface;
        }
        .-compact #task-layout {
            grid-size: 1 2;
            grid-columns: 1fr;
            grid-rows: auto auto;
        }
        #stage-map, #recent, #output {
            margin-top: 1;
        }
        #details {
            width: 100%;
            max-width: 104;
            margin-bottom: 1;
            border: round $secondary;
            height: 1fr;
            display: none;
        }
        """
        BINDINGS = [
            ("l", "toggle_details", "详情"),
            ("f", "open_output_directory", "输出目录"),
            ("d", "open_diagnostics", "诊断日志"),
            ("escape", "show_overview", "返回概览"),
            Binding("q", "quit_observer", "退出观察", priority=True),
            ("x", "cancel_task", "停止任务"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._task_running = True

        def compose(self) -> ComposeResult:
            with VerticalScroll(id="task-panel"):
                yield Static(self.build_status_text(), id="status")
                yield ProgressBar(total=100, show_eta=False, id="progress")
                yield Static("", id="current-work")
                with Grid(id="task-layout"):
                    with Vertical(id="pipeline-pane"):
                        yield Static("", id="stage-map")
                    with Vertical(id="activity-pane"):
                        yield Static("", id="recent")
                        yield Static("", id="output")
                        yield Static("", id="action-status")
            yield RichLog(max_lines=200, auto_scroll=True, id="details")
            yield Footer()

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
            presentation = build_task_presentation(
                state,
                returncode=returncode,
                output_path=output_path,
                now=time.time(),
            )
            return build_task_status_text(presentation)

        def refresh_from_log(self) -> None:
            rows = iter_event_log(log_path)
            state = _summarize_event_rows(rows)
            returncode = process.poll()
            presentation = build_task_presentation(
                state,
                returncode=returncode,
                output_path=output_path,
                now=time.time(),
            )
            self._task_running = returncode is None
            self.refresh_bindings()
            self.query_one("#status", Static).update(
                build_task_status_text(presentation)
            )

            bar = self.query_one("#progress", ProgressBar)
            if presentation.progress is None:
                bar.update(total=None)
            else:
                bar.update(total=100, progress=presentation.progress)
            self.query_one("#stage-map", Static).update(
                "[b]处理流程[/b]\n" + "\n".join(presentation.stage_lines)
            )
            self.query_one("#current-work", Static).update(presentation.current_work)

            recent_text = "\n".join(f"  {text}" for text in presentation.recent_texts)
            self.query_one("#recent", Static).update(
                f"[b]最近字幕[/b]\n{recent_text or '  暂无'}"
            )
            self.query_one("#output", Static).update(presentation.output_text)

            details = self.query_one("#details", RichLog)
            details.clear()
            for row in rows[-50:]:
                data = row.get("data") or {}
                message = data.get("message_zh") or row.get("event_type", "未知事件")
                details.write(f"{data.get('stage', '-'):>8}  {message}")

        def action_toggle_details(self) -> None:
            details = self.query_one("#details", RichLog)
            details.display = not details.display
            self.query_one("#task-panel").display = not details.display

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
            self.query_one("#task-panel").display = True

        def action_quit_observer(self) -> None:
            self.exit("quit")

        def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
            if action == "cancel_task":
                return self._task_running
            return True

        def action_cancel_task(self) -> None:
            if process.poll() is None:
                self.push_screen(CancelTaskScreen(), self._finish_cancel)

        def _finish_cancel(self, confirmed: bool | None) -> None:
            if confirmed and process.poll() is None:
                self.exit("interrupt")
            elif confirmed:
                self.refresh_from_log()

    return ObserverDashboard()
