"""Native Textual pages that keep the v2 workbench inside one application."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import uuid

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Input,
    OptionList,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from subtap.cli.hotword_cli import _open_file_cross_platform
from subtap.cli.pipeline_cli import (
    _observer_process_matches_run_id,
    _record_interrupted_task,
    _safe_remove_recent_task,
    _stop_observer_child,
    _stop_observer_process_group,
)
from subtap.batch_interactive import MEDIA_EXTENSIONS, scan_directory
from subtap.core.models import ModelRegistry
from subtap.core.state_store import StateStore
from subtap.schemas.glossary import (
    load_glossary,
    remove_plain_glossary_entry,
    save_glossary,
    upsert_plain_glossary_terms,
)
from subtap.schemas.config import load_config
from subtap.ui.config_manager import ConfigManager
from subtap.ui.native_picker import choose_file, choose_folder
from subtap.ui.views.wizard import WizardView
from subtap.ui.observer import (
    TaskState,
    LIVE_STATUSES,
    EventLogCursor,
    _summarize_event_rows,
    _UNSET,
    build_observation_error_presentation,
    build_task_presentation,
    build_task_presentation_from_log,
    iter_event_log,
    persisted_process_matches_task,
)

from .components import PageHeader
from .task_views import TaskScreen, TaskView
from .theme import HORIZONTAL_BREAKPOINTS


class DeskScreen(Screen[None]):
    """Shared page shell and one-level navigation."""

    HORIZONTAL_BREAKPOINTS = HORIZONTAL_BREAKPOINTS
    BINDINGS = [Binding("escape", "back", "返回", priority=True)]

    def action_back(self) -> None:
        self.app.pop_screen()


class BatchScreen(DeskScreen):
    """Configure a directory batch without leaving the workbench."""

    def __init__(self) -> None:
        super().__init__()
        self.input_dir: Path | None = None
        self.output_dir = Path.cwd() / "output"
        self._process: subprocess.Popen | None = None
        default_glossary = Path.home() / ".subtap" / "glossaries" / "default.txt"
        self._glossary_options = [
            ("默认热词表 · default.txt", str(default_glossary)),
            *[
                (f"本地热词表 · {path.name}", str(path))
                for path in WizardView.list_glossaries()
                if path.suffix.casefold() == ".txt"
                and path.name not in {"default.txt", "learned.txt"}
            ],
        ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="desk-shell"):
            yield PageHeader("批量转录", "选择媒体目录，所有文件使用同一套字幕设置。")
            yield Static("媒体目录", classes="desk-label")
            with Horizontal(classes="desk-row"):
                yield Static("尚未选择目录", id="batch-path", classes="desk-value")
                yield Button("选择…", id="choose-batch")
            yield Static("任务设置", classes="desk-label")
            yield Select(
                [("快速 · 0.6B", "fast"), ("高质量 · 1.7B", "quality")],
                value="quality",
                id="batch-quality",
            )
            yield Static("热词表", classes="desk-label")
            yield Select(
                self._glossary_options,
                value=self._glossary_options[0][1],
                id="batch-glossary",
            )
            yield Static("输出目录", classes="desk-label")
            with Horizontal(classes="desk-row"):
                yield Static(
                    str(self.output_dir), id="batch-output", classes="desk-value"
                )
                yield Button("选择…", id="choose-batch-output")
            yield Static("选择目录后会显示文件数量和预计输出位置。", id="batch-status")
            with Horizontal(classes="desk-actions"):
                yield Button("返回", id="back")
                yield Button(
                    "开始批量转录",
                    id="review-batch",
                    variant="primary",
                    disabled=True,
                )
        yield Footer(compact=True, show_command_palette=False)

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.action_back()

    @on(Button.Pressed, "#choose-batch")
    def choose_batch(self) -> None:
        selected = choose_folder("选择媒体目录")
        if selected is None:
            return
        self.input_dir = selected
        count = len(scan_directory(selected))
        unsupported = [
            path.name
            for path in sorted(selected.iterdir())
            if path.is_file() and path.suffix.casefold() not in MEDIA_EXTENSIONS
        ]
        self.query_one("#batch-path", Static).update(str(selected))
        unsupported_text = (
            f"；另有 {len(unsupported)} 个不可处理：" f"{', '.join(unsupported[:3])}"
            if unsupported
            else ""
        )
        self.query_one("#batch-status", Static).update(
            f"找到 {count} 个媒体文件{unsupported_text}"
        )
        self.query_one("#review-batch", Button).disabled = count == 0

    @on(Button.Pressed, "#choose-batch-output")
    def choose_batch_output(self) -> None:
        selected = choose_folder("选择输出目录")
        if selected is None:
            return
        self.output_dir = selected
        self.query_one("#batch-output", Static).update(str(selected))

    @on(Button.Pressed, "#review-batch")
    def start_batch(self) -> None:
        if self.input_dir is None:
            raise RuntimeError("批量转录缺少媒体目录")
        quality = self.query_one("#batch-quality", Select).value
        if quality not in {"fast", "quality"}:
            raise RuntimeError("批量转录质量设置无效")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        task_id = f"batch-{uuid.uuid4().hex}"
        task_dir = Path.home() / ".subtap" / "jobs" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.output_dir / "manifest.json"
        log_path = task_dir / "batch.log"
        command = [
            sys.executable,
            "-m",
            "subtap.cli",
            "batch-transcribe",
            "--dir",
            str(self.input_dir),
            "--mode",
            str(quality),
            "--output-dir",
            str(self.output_dir),
            "--no-confirm",
        ]
        glossary_path = self.query_one("#batch-glossary", Select).value
        if not isinstance(glossary_path, str):
            raise RuntimeError("批量转录热词表设置无效")
        if Path(glossary_path).is_file():
            glossary = load_glossary(Path(glossary_path))
            hotwords = [
                value
                for term in glossary.terms
                for value in (term.canonical, *term.aliases)
            ]
            if hotwords:
                command.extend(["--hotwords", ",".join(hotwords)])
        state_store = StateStore(Path.home() / ".subtap" / "state.json")
        state_store.add_recent_task(
            task_id,
            f"{self.input_dir.name}（批量）",
            str(manifest_path),
            log_path=str(log_path),
            diagnostic_path=str(log_path),
            status="starting",
        )
        try:
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    command,
                    start_new_session=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env={
                        **os.environ,
                        "SUBTAP_RUN_ID": task_id,
                    },
                )
        except BaseException:
            _safe_remove_recent_task(task_id)
            raise
        self._process = process
        try:
            if not state_store.attach_recent_task_process(task_id, process.pid):
                raise RuntimeError("批量任务状态记录在启动期间丢失")
        except BaseException:
            _stop_observer_child(process)
            self._process = None
            _safe_remove_recent_task(task_id)
            raise
        register_process = getattr(self.app, "register_batch_process", None)
        if register_process is not None:
            register_process(task_id, process)
        for selector in (
            "#choose-batch",
            "#choose-batch-output",
            "#review-batch",
            "#batch-quality",
            "#batch-glossary",
        ):
            self.query_one(selector).disabled = True
        self.query_one("#batch-status", Static).update(
            f"运行中 · 结果将写入 {self.output_dir}"
        )
        self.app.push_screen(
            BatchTaskScreen(
                self._process,
                manifest_path,
                log_path,
                task_id,
            )
        )


class BatchTaskScreen(DeskScreen):
    """Observe one batch with the same status vocabulary as single tasks."""

    BINDINGS = [
        Binding("escape", "back", "返回", priority=True),
        ("x", "interrupt_batch", "停止任务"),
    ]

    def __init__(
        self,
        process,
        manifest_path: Path,
        log_path: Path,
        task_id: str | None = None,
        *,
        persisted_live: bool = False,
        persisted_pid: int | None = None,
    ) -> None:
        super().__init__()
        self.process = process
        self.manifest_path = manifest_path
        self.log_path = log_path
        self.task_id = task_id
        self._items: list[dict] = []
        self._interrupted = False
        self._refresh_timer: Timer | None = None
        self._manifest_signature: tuple[int, int, int] | None = None
        self._cached_summary: str | None = None
        self._cached_manifest_status: str | None = None
        self._previous_batch_status: str | None = None
        self._persisted_status = (
            "running" if process is not None or persisted_live else "observation_error"
        )
        self._persisted_pid = persisted_pid
        self._persisted_live = persisted_live

    def compose(self) -> ComposeResult:
        with Vertical(classes="desk-shell"):
            yield PageHeader("批量任务", "逐个处理已选择的媒体文件。")
            yield Static("状态：准备中", id="batch-run-status", classes="desk-note")
            yield OptionList(
                Option("等待任务清单…", disabled=True),
                id="batch-run-items",
            )
            yield Static(
                f"输出目录\n{self.manifest_path.parent}",
                classes="desk-value",
            )
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        self.refresh_batch()
        if self._persisted_status in LIVE_STATUSES:
            self._refresh_timer = self.set_interval(1.0, self.refresh_batch)

    def _manifest_signature_for_current_file(self) -> tuple[int, int, int] | None:
        try:
            stat = self.manifest_path.stat()
        except FileNotFoundError:
            return None
        return stat.st_ino, stat.st_mtime_ns, stat.st_size

    def _refresh_manifest_items(self) -> tuple[str, str | None]:
        """Load manifest and rebuild OptionList. Returns (summary, batch_status)."""
        from subtap.batch import load_manifest

        manifest = load_manifest(self.manifest_path)
        self._items = list(manifest["items"])
        batch_status = self._manifest_status(manifest)
        item_list = self.query_one("#batch-run-items", OptionList)
        item_list.clear_options()
        item_list.add_options(
            [
                Option(
                    f"{self._item_marker(item)} " f"{Path(item['input_path']).name}",
                    id=f"item-{index}",
                )
                for index, item in enumerate(self._items)
            ]
        )
        summary = (
            f"成功 {manifest['succeeded']} · 失败 {manifest['failed']}"
            f" · 已停止 {manifest['interrupted']}"
        )
        self._cached_summary = summary
        self._cached_manifest_status = batch_status
        return summary, batch_status

    def refresh_batch(self) -> None:
        status = self.query_one("#batch-run-status", Static)
        batch_status = None
        summary: str

        if self.manifest_path.is_file():
            signature = self._manifest_signature_for_current_file()
            if (
                signature is not None
                and signature == self._manifest_signature
                and self._cached_summary is not None
            ):
                summary = self._cached_summary
                batch_status = self._cached_manifest_status
            else:
                summary, batch_status = self._refresh_manifest_items()
                self._manifest_signature = signature
        else:
            summary = "正在建立任务清单"

        returncode = self.process.poll() if self.process is not None else None
        if self.process is not None and returncode is None and not self._interrupted:
            batch_status = "running"
        elif self._interrupted:
            batch_status = "interrupted"
        elif self.process is not None and returncode != 0:
            batch_status = "failed"
        elif (
            batch_status in LIVE_STATUSES
            and self.process is None
            and self._persisted_status == "observation_error"
        ):
            batch_status = "observation_error"
        elif batch_status is None:
            batch_status = self._stored_status() or "observation_error"

        # When no app-owned process exists, verify the persisted process identity.
        # Dead PID or mismatched run-id → the batch cannot still be running.
        if (
            self.process is None
            and self._persisted_pid is not None
            and batch_status in LIVE_STATUSES
            and not persisted_process_matches_task(self._persisted_pid, self.task_id)
        ):
            batch_status = "observation_error"

        labels = {
            "starting": "准备中",
            "running": "运行中",
            "stopping": "正在停止",
            "completed": "已完成",
            "partial_failure": "部分失败",
            "failed": "失败",
            "interrupted": "已中断",
            "observation_error": "状态未知",
        }
        if batch_status == "failed" and returncode not in {None, 0}:
            status.update(
                f"状态：失败（退出码 {returncode}） · {summary}\n"
                f"诊断日志：{self.log_path}"
            )
        elif batch_status == "observation_error":
            status.update(f"状态：状态未知 · {summary}\n诊断日志：{self.log_path}")
        else:
            status.update(f"状态：{labels[batch_status]} · {summary}")
        self._persist_status(batch_status)
        if batch_status not in LIVE_STATUSES and self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None
        if batch_status != self._previous_batch_status:
            self.refresh_bindings()
            self._previous_batch_status = batch_status

    @staticmethod
    def _manifest_status(manifest: dict) -> str:
        statuses = {str(item.get("status")) for item in manifest["items"]}
        if statuses & {"pending", "running"}:
            return "running"
        if manifest["failed"] and manifest["succeeded"]:
            return "partial_failure"
        if manifest["failed"]:
            return "failed"
        if manifest["interrupted"]:
            return "interrupted"
        if manifest["items"] and manifest["succeeded"] == len(manifest["items"]):
            return "completed"
        return "observation_error"

    def _stored_status(self) -> str | None:
        if self.task_id is None:
            return None
        return next(
            (
                str(task.get("status"))
                for task in StateStore(Path.home() / ".subtap" / "state.json")
                .load()
                .recent_tasks
                if str(task.get("task_id")) == self.task_id
            ),
            None,
        )

    def _persist_status(self, status: str) -> None:
        if self.task_id is None or status == self._persisted_status:
            return
        StateStore(Path.home() / ".subtap" / "state.json").update_recent_task_status(
            self.task_id,
            status,
        )
        self._persisted_status = status

    @staticmethod
    def _item_marker(item: dict) -> str:
        return {
            "succeeded": "✓",
            "failed": "×",
            "interrupted": "■",
            "running": "▶",
            "pending": "·",
        }.get(str(item.get("status")), "?")

    @on(OptionList.OptionSelected, "#batch-run-items")
    def open_item(self, event: OptionList.OptionSelected) -> None:
        index = int((event.option.id or "").removeprefix("item-"))
        self.app.push_screen(BatchItemScreen(self._items[index]))

    def action_interrupt_batch(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        from .observer import InterruptTaskScreen

        self.app.push_screen(InterruptTaskScreen(), self._finish_interrupt)

    def _finish_interrupt(self, confirmed: bool | None) -> None:
        if not confirmed or self.process is None or self.process.poll() is not None:
            return
        _stop_observer_child(self.process)
        self._interrupted = True
        self.refresh_batch()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "interrupt_batch":
            return self.process is not None and self.process.poll() is None
        return True

    def on_unmount(self) -> None:
        if self._refresh_timer is not None:
            self._refresh_timer.stop()
            self._refresh_timer = None


class BatchItemScreen(DeskScreen):
    """Show one batch item without leaking raw manifest JSON."""

    def __init__(self, item: dict) -> None:
        super().__init__()
        self.item = item

    def compose(self) -> ComposeResult:
        status = {
            "succeeded": "已完成",
            "failed": "失败",
            "interrupted": "已中断",
            "running": "运行中",
            "pending": "等待中",
        }.get(str(self.item.get("status")), "状态未知")
        with Vertical(classes="desk-shell"):
            yield PageHeader(Path(self.item["input_path"]).name, status)
            yield Static(
                f"输入\n{self.item['input_path']}\n\n"
                f"输出\n{self.item.get('output_dir', '尚未生成')}\n\n"
                f"耗时\n{float(self.item.get('duration') or 0):.1f} 秒",
                classes="resource-card",
            )
            if self.item.get("error"):
                yield Static(
                    f"失败原因\n{self.item['error']}",
                    classes="resource-card blocked",
                )
        yield Footer(compact=True, show_command_palette=False)


class TasksScreen(DeskScreen):
    """Discover persisted runs through the existing StateStore."""

    def __init__(self, auto_open_task_id: str | None = None) -> None:
        super().__init__()
        self.auto_open_task_id = auto_open_task_id
        self.tasks: list[dict] = []

    def compose(self) -> ComposeResult:
        store = StateStore(Path.home() / ".subtap" / "state.json")
        self.tasks = store.load().recent_tasks
        terminal_batch_statuses = {
            "completed",
            "success",
            "failed",
            "partial_failure",
            "interrupted",
        }
        for task in self.tasks:
            if not str(task.get("task_id", "")).startswith("batch-"):
                continue
            status = str(task.get("status") or "")
            if status in terminal_batch_statuses:
                continue
            manifest_path = Path(task.get("output_path") or "__missing__")
            if not manifest_path.is_file():
                continue
            from subtap.batch import load_manifest

            try:
                manifest_status = BatchTaskScreen._manifest_status(
                    load_manifest(manifest_path)
                )
            except (OSError, ValueError, KeyError):
                task["status"] = "observation_error"
                continue
            if (
                manifest_status not in {"starting", "running", "stopping"}
                and task.get("status") != manifest_status
            ):
                store.update_recent_task_status(
                    str(task["task_id"]),
                    manifest_status,
                )
                task["status"] = manifest_status
        with Vertical(classes="desk-shell"):
            yield PageHeader("任务记录", "运行中与历史任务")
            yield OptionList(
                *(
                    [
                        Option(
                            f"{task.get('input_name', '未知文件')}  ·  "
                            f"{self._task_state(task)}  ·  "
                            f"{self._task_time(task)}  ·  "
                            f"{'输出可用' if Path(task.get('output_path') or '__missing__').is_file() else '暂无输出'}",
                            id=str(task.get("task_id")),
                        )
                        for task in self.tasks
                    ]
                    if self.tasks
                    else [Option("暂无任务记录", disabled=True)]
                ),
                id="task-list",
            )
            if not self.tasks:
                yield Button("新建字幕", id="empty-new-task", variant="primary")
        yield Footer(compact=True, show_command_palette=False)

    @staticmethod
    def _task_time(task: dict) -> str:
        def display(value: object) -> str | None:
            if not isinstance(value, str):
                return None
            try:
                return (
                    datetime.fromisoformat(value).astimezone().strftime("%m-%d %H:%M")
                )
            except ValueError:
                return None

        started = display(task.get("started_at"))
        completed = display(task.get("completed_at"))
        if completed is not None:
            return f"完成 {completed}"
        if started is not None:
            return f"开始 {started}"
        return "时间未记录"

    @on(Button.Pressed, "#empty-new-task")
    def new_task_from_empty_state(self) -> None:
        from .new_transcription import NewTranscriptionScreen

        self.app.push_screen(NewTranscriptionScreen(), self._finish_new_task)

    def _finish_new_task(self, command: list[str] | None) -> None:
        if command is None:
            return
        start_transcription = getattr(self.app, "start_transcription", None)
        if start_transcription is None:
            raise RuntimeError("当前应用无法启动转录任务")
        start_transcription(command)

    def on_mount(self) -> None:
        if self.auto_open_task_id is None:
            return
        task = next(
            (
                task
                for task in self.tasks
                if str(task.get("task_id")) == self.auto_open_task_id
            ),
            None,
        )
        if task is None:
            self.notify(
                f"未找到任务：{self.auto_open_task_id}",
                severity="error",
            )
            return
        self.call_after_refresh(lambda: self.open_task_record(task))

    @staticmethod
    def _task_state(task: dict) -> str:
        output = Path(task.get("output_path") or "__missing__")
        log = Path(task.get("log_path") or "__missing__")
        status = str(task.get("status") or "")
        labels = {
            "starting": "准备中",
            "running": "运行中",
            "stopping": "正在停止",
            "completed": "已完成",
            "success": "已完成",
            "failed": "失败",
            "partial_failure": "部分失败",
            "interrupted": "已中断",
            "recorded": "任务记录",
            "observation_error": "状态未知",
        }
        terminal_labels = {
            "completed": "已完成",
            "success": "已完成",
            "failed": "失败",
            "partial_failure": "部分失败",
            "interrupted": "已中断",
        }
        live_statuses = LIVE_STATUSES

        if str(task.get("task_id", "")).startswith("batch-"):
            if status in live_statuses:
                from .home import _is_live_task

                if not _is_live_task(task):
                    StateStore(
                        Path.home() / ".subtap" / "state.json"
                    ).update_recent_task_status(
                        str(task["task_id"]),
                        "observation_error",
                    )
                    return "状态未知"
            return labels.get(status, "状态未知")

        if status in terminal_labels:
            return terminal_labels[status]

        if status in live_statuses:
            from .home import _is_live_task

            if not _is_live_task(task):
                # PID dead — attempt log-driven terminal state reconciliation.
                if log.is_file():
                    try:
                        presentation = build_task_presentation_from_log(
                            log,
                            output_path=output,
                        )
                    except (OSError, ValueError):
                        pass
                    else:
                        terminal = {
                            TaskState.COMPLETED: "completed",
                            TaskState.FAILED: "failed",
                            TaskState.INTERRUPTED: "interrupted",
                        }.get(presentation.state)
                        if terminal is not None:
                            StateStore(
                                Path.home() / ".subtap" / "state.json"
                            ).update_recent_task_status(
                                str(task["task_id"]),
                                terminal,
                            )
                            return labels[terminal]
                return "状态未知"
            return labels[status]

        if status in labels:
            return labels[status]

        if log.is_file():
            try:
                presentation = build_task_presentation_from_log(
                    log,
                    output_path=output,
                )
            except (OSError, ValueError):
                return "状态未知"
            if presentation.state == TaskState.RECORDED and status in live_statuses:
                return labels[status]
            return {
                TaskState.RUNNING: "运行中",
                TaskState.COMPLETED: "已完成",
                TaskState.FAILED: "失败",
                TaskState.INTERRUPTED: "已中断",
                TaskState.OBSERVATION_ERROR: "状态未知",
                TaskState.RECORDED: "任务记录",
            }[presentation.state]

        if output.is_file():
            return "已完成"
        return "记录不完整"

    @on(OptionList.OptionSelected, "#task-list")
    def open_task(self, event: OptionList.OptionSelected) -> None:
        task = next(
            (
                task
                for task in self.tasks
                if str(task.get("task_id")) == event.option.id
            ),
            None,
        )
        if task is None:
            return
        self.open_task_record(task)

    def open_task_record(self, task: dict) -> None:
        """Open one persisted task through the shared Tasks detail path."""
        log_path = Path(task.get("log_path") or "__missing__")
        task_id = str(task.get("task_id", ""))
        if str(task.get("task_id", "")).startswith("batch-"):
            from .home import _is_live_task

            get_process = getattr(self.app, "get_batch_process", None)
            process = get_process(str(task["task_id"])) if get_process else None
            self.app.push_screen(
                BatchTaskScreen(
                    process,
                    Path(task.get("output_path") or "__missing__"),
                    log_path,
                    str(task["task_id"]),
                    persisted_live=_is_live_task(task),
                    persisted_pid=(
                        int(task["pid"]) if isinstance(task.get("pid"), int) else None
                    ),
                )
            )
            return
        resume_observer = getattr(self.app, "resume_observer", None)
        if resume_observer is not None and resume_observer(task_id):
            return
        if not log_path.is_file():
            self.notify(f"未找到任务日志：{log_path}", severity="error")
            return
        self.app.push_screen(
            RecordedTaskScreen(
                log_path,
                Path(task["output_path"]) if task.get("output_path") else None,
                (
                    Path(task["diagnostic_path"])
                    if task.get("diagnostic_path")
                    else None
                ),
                (
                    int(task["pid"])
                    if isinstance(task.get("pid"), int)
                    and task.get("status") in LIVE_STATUSES
                    else None
                ),
                task_id=task_id,
            )
        )


class RecordedTaskScreen(TaskScreen):
    """Refresh a persisted task without owning or stopping its process."""

    BINDINGS = [
        Binding("escape", "back", "返回", priority=True),
        Binding("x", "interrupt_task", "停止任务", priority=True),
        ("o", "open_output_file", "打开字幕"),
        ("f", "open_output_directory", "输出目录"),
        ("d", "open_diagnostics", "诊断日志"),
        ("n", "new_task", "新建任务"),
    ]

    def __init__(
        self,
        log_path: Path,
        output_path: Path | None,
        diagnostic_path: Path | None = None,
        pid: int | None = None,
        task_id: str | None = None,
    ) -> None:
        self.log_path = log_path
        self.output_path = output_path
        self.diagnostic_path = diagnostic_path
        self.pid = pid
        self.task_id = task_id
        self._event_cursor: EventLogCursor | None = (
            EventLogCursor(log_path, recent_limit=12, expected_run_id=task_id)
            if pid is not None and persisted_process_matches_task(pid, task_id)
            else None
        )
        self._refresh_timer: Timer | None = None
        super().__init__(self._build_presentation())

    def _build_presentation(self):
        """Build from cursor (live task) or cold read (static/historical task)."""
        if self._event_cursor is not None:
            try:
                self._event_cursor.read_updates()
                state = self._event_cursor.state
            except ValueError as error:
                previous = getattr(self, "presentation", None)
                return build_observation_error_presentation(error, previous)

            pipeline_status = state.get("pipeline_status")

            if pipeline_status:
                self.pid = None
                if pipeline_status == "completed":
                    returncode = 0
                elif pipeline_status == "interrupted":
                    returncode = _UNSET
                else:
                    returncode = 1
                return build_task_presentation(
                    state,
                    returncode=returncode,
                    output_path=self.output_path,
                    now=time.time(),
                )

            if self.pid is not None and persisted_process_matches_task(
                self.pid, self.task_id
            ):
                return build_task_presentation(
                    state,
                    returncode=None,
                    output_path=self.output_path,
                    now=time.time(),
                )

            self.pid = None
            recorded = build_task_presentation(
                state,
                returncode=_UNSET,
                output_path=self.output_path,
                now=time.time(),
            )
            return build_observation_error_presentation(
                RuntimeError("无法确认任务进程仍在运行"),
                recorded,
            )

        # Cold read: validate every schema-v2 row matches expected_run_id.
        try:
            cold_cursor = EventLogCursor(
                self.log_path,
                recent_limit=12,
                expected_run_id=self.task_id,
            )
            cold_cursor.read_initial()
            state = cold_cursor.state
        except (OSError, ValueError) as error:
            previous = getattr(self, "presentation", None)
            return build_observation_error_presentation(error, previous)

        # Pipeline terminal event wins over PID/process identity.
        pipeline_status = state.get("pipeline_status")
        if pipeline_status:
            self.pid = None
            if pipeline_status == "completed":
                returncode = 0
            elif pipeline_status == "interrupted":
                returncode = _UNSET
            else:
                returncode = 1
            return build_task_presentation(
                state,
                returncode=returncode,
                output_path=self.output_path,
                now=time.time(),
            )

        if self.pid is not None:
            if persisted_process_matches_task(self.pid, self.task_id):
                return build_task_presentation(
                    state,
                    returncode=None,
                    output_path=self.output_path,
                    now=time.time(),
                )
            recorded = build_task_presentation(
                state,
                returncode=_UNSET,
                output_path=self.output_path,
                now=time.time(),
            )
            return build_observation_error_presentation(
                RuntimeError("无法确认任务进程仍在运行"),
                recorded,
            )

        # No PID — historical record, static presentation.
        return build_task_presentation(
            state,
            returncode=_UNSET,
            output_path=self.output_path,
            now=time.time(),
        )

    def _stop_refresh_timer(self) -> None:
        timer = self._refresh_timer
        if timer is None:
            return
        timer.stop()
        self._refresh_timer = None

    def compose(self) -> ComposeResult:
        yield TaskView(self.presentation)
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        if (
            self._event_cursor is not None
            and self.presentation.state is TaskState.RUNNING
        ):
            self._refresh_timer = self.set_interval(1.0, self.refresh_task)

    async def refresh_task(self) -> None:
        presentation = self._build_presentation()
        await self.update_presentation(presentation)
        if presentation.state is not TaskState.RUNNING:
            self._stop_refresh_timer()

    def on_unmount(self) -> None:
        self._stop_refresh_timer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "new_task":
            return "new_task" in self.presentation.allowed_actions
        if action == "interrupt_task":
            return "stop" in self.presentation.allowed_actions
        return True

    def action_interrupt_task(self) -> None:
        if (
            self.pid is None
            or self.task_id is None
            or self.presentation.state is not TaskState.RUNNING
        ):
            return
        if not _observer_process_matches_run_id(self.pid, self.task_id):
            self.notify(
                "无法确认该进程仍属于此任务，已拒绝停止。",
                severity="error",
            )
            return
        from .observer import InterruptTaskScreen

        self.app.push_screen(InterruptTaskScreen(), self._finish_interrupt)

    def _finish_interrupt(self, confirmed: bool | None) -> None:
        if not confirmed or self.pid is None or self.task_id is None:
            return
        if not _observer_process_matches_run_id(self.pid, self.task_id):
            self.notify(
                "任务进程身份已变化，已拒绝停止。",
                severity="error",
            )
            return
        _stop_observer_process_group(self.pid)
        state = _summarize_event_rows(iter_event_log(self.log_path))
        if state.get("pipeline_status") != "interrupted":
            task_id = state.get("run_id")
            if task_id is None:
                raise RuntimeError("无法记录中断状态：任务标识缺失")
            started_at = state.get("started_at")
            _record_interrupted_task(
                self.log_path,
                str(task_id),
                total_duration_sec=(
                    max(0.0, time.time() - float(started_at))
                    if started_at is not None
                    else 0.0
                ),
            )
        self.pid = None
        self.call_after_refresh(self.refresh_task)

    def _open_path(self, path: Path, label: str) -> None:
        try:
            _open_file_cross_platform(path)
        except (OSError, subprocess.SubprocessError) as error:
            self.notify(f"打开{label}失败：{error}", severity="error")
            return
        self.notify(f"已打开{label}。")

    def action_open_output_file(self) -> None:
        if self.output_path is None or not self.output_path.is_file():
            self.notify("没有可打开的字幕结果。", severity="warning")
            return
        self._open_path(self.output_path, "字幕")

    def action_open_output_directory(self) -> None:
        if self.output_path is None or not self.output_path.parent.is_dir():
            self.notify("没有可打开的输出目录。", severity="warning")
            return
        self._open_path(self.output_path.parent, "输出目录")

    def action_open_diagnostics(self) -> None:
        if self.diagnostic_path is None or not self.diagnostic_path.is_file():
            self.notify("未找到诊断日志。", severity="warning")
            return
        self._open_path(self.diagnostic_path, "诊断日志")


class ModelsScreen(DeskScreen):
    """Readable model inventory built from ModelRegistry."""

    def __init__(self) -> None:
        super().__init__()
        self._model_process: subprocess.Popen | None = None
        self._model_timer: Timer | None = None
        self._model_operation: str | None = None

    def compose(self) -> ComposeResult:
        config = load_config(
            Path.home() / ".subtap" / "config.yaml",
            warn_deprecated=False,
        )
        statuses = ModelRegistry(config).status()
        labels = {
            "asr_0.6b": "快速模式 · 0.6B",
            "asr_1.7b": "高质量模式 · 1.7B",
            "aligner": "时间轴精对齐",
        }
        with VerticalScroll(classes="desk-shell"):
            yield PageHeader("模型管理", "选择质量时，所需模型必须处于可用状态。")
            details = []
            for status in statuses:
                marker = "✓ 文件齐全" if status.installed else "! 文件不完整"
                default = "  ·  当前默认" if status.name == config.asr.model else ""
                yield Static(
                    f"{labels.get(status.name, status.name)}\n" f"{marker}{default}",
                    classes=(
                        "resource-card success"
                        if status.installed
                        else "resource-card blocked"
                    ),
                )
                if not status.installed:
                    yield Button(
                        f"安装 {labels.get(status.name, status.name)}",
                        id=f"install-{status.name.replace('.', '-')}",
                        name=status.name,
                        classes="model-install",
                    )
                details.append(f"{labels.get(status.name, status.name)}\n{status.path}")
            yield Collapsible(
                Static("\n\n".join(details)),
                title="安装位置与检查详情",
                collapsed=True,
            )
            yield Static(
                "模型只在对应处理阶段加载，阶段结束后释放。",
                classes="desk-note",
            )
            yield Static("", id="model-status", classes="desk-note")
            yield Button("完整校验", id="verify-models", variant="primary")
            yield Button("刷新文件状态", id="refresh-models")
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        get_process = getattr(self.app, "get_model_process", None)
        owned = get_process() if get_process is not None else None
        if owned is None:
            return
        self._model_process, self._model_operation = owned
        self.query_one("#model-status", Static).update(
            f"{self._model_operation}正在进行，完成后将自动更新。"
        )
        self.query_one("#verify-models", Button).disabled = True
        for button in self.query(".model-install"):
            button.disabled = True
        self._model_timer = self.set_interval(1.0, self.refresh_model_operation)
        self.refresh_model_operation()

    def _register_model_process(self) -> None:
        if self._model_process is None or self._model_operation is None:
            raise RuntimeError("模型操作状态不完整")
        register_process = getattr(self.app, "register_model_process", None)
        if register_process is not None:
            register_process(self._model_process, self._model_operation)

    @on(Button.Pressed, ".model-install")
    def install_model(self, event: Button.Pressed) -> None:
        if self._model_process is not None and self._model_process.poll() is None:
            self.notify("已有模型正在安装。", severity="warning")
            return
        model_name = event.button.name or ""
        if not model_name:
            raise RuntimeError("模型安装动作缺少模型名称")
        log_dir = Path.home() / ".subtap" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "model-install.log").open("w", encoding="utf-8") as log:
            self._model_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "subtap.cli",
                    "models",
                    "install",
                    model_name,
                ],
                start_new_session=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        self.query_one("#model-status", Static).update(
            f"正在安装 {model_name}，完成后将自动重新检查。"
        )
        for button in self.query(".model-install"):
            button.disabled = True
        self.query_one("#verify-models", Button).disabled = True
        self._model_operation = "安装"
        self._register_model_process()
        self._model_timer = self.set_interval(1.0, self.refresh_model_operation)

    @on(Button.Pressed, "#verify-models")
    def verify_models(self) -> None:
        if self._model_process is not None and self._model_process.poll() is None:
            self.notify("模型操作正在进行。", severity="warning")
            return
        log_dir = Path.home() / ".subtap" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "model-verify.log").open("w", encoding="utf-8") as log:
            self._model_process = subprocess.Popen(
                [sys.executable, "-m", "subtap.cli", "models", "verify"],
                start_new_session=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        self._model_operation = "完整校验"
        self._register_model_process()
        self.query_one("#model-status", Static).update("正在逐文件校验模型完整性…")
        self.query_one("#verify-models", Button).disabled = True
        for button in self.query(".model-install"):
            button.disabled = True
        self._model_timer = self.set_interval(1.0, self.refresh_model_operation)

    def refresh_model_operation(self) -> None:
        if self._model_process is None:
            return
        returncode = self._model_process.poll()
        if returncode is None:
            return
        if self._model_timer is not None:
            self._model_timer.stop()
            self._model_timer = None
        operation = self._model_operation or "模型操作"
        completed_process = self._model_process
        self._model_process = None
        self._model_operation = None
        clear_process = getattr(self.app, "clear_model_process", None)
        if clear_process is not None:
            clear_process(completed_process)
        if returncode != 0:
            self.query_one("#model-status", Static).update(
                f"{operation}失败，请查看 ~/.subtap/logs/model-"
                f"{'verify' if operation == '完整校验' else 'install'}.log"
            )
            for button in self.query(".model-install"):
                button.disabled = False
            self.query_one("#verify-models", Button).disabled = False
            return
        if operation == "完整校验":
            self.query_one("#model-status", Static).update("✓ 完整校验通过")
            self.query_one("#verify-models", Button).disabled = False
            return
        self.refresh(recompose=True)

    def on_unmount(self) -> None:
        if self._model_timer is not None:
            self._model_timer.stop()
            self._model_timer = None

    @on(Button.Pressed, "#refresh-models")
    def refresh_models(self) -> None:
        self.refresh(recompose=True)


class HotwordsScreen(DeskScreen):
    """Separate user-maintained and learned hotword files."""

    def compose(self) -> ComposeResult:
        root = Path.home() / ".subtap" / "glossaries"
        learned_path = root / "learned.txt"
        learned_error = None
        try:
            self._learned_terms = load_glossary(learned_path).terms
        except (OSError, ValueError) as error:
            self._learned_terms = []
            learned_error = str(error)
        with VerticalScroll(classes="desk-shell"):
            yield PageHeader(
                "热词管理",
                "默认热词由你维护；自动学习结果由系统更新。",
            )
            yield Static("我的默认热词", classes="desk-label")
            yield Static(str(root / "default.txt"), classes="desk-value")
            yield Button("用文本编辑器打开", id="open-default", variant="primary")
            yield Static("自动学习结果", classes="desk-label")
            yield Static(str(learned_path), classes="desk-value")
            if learned_error is not None:
                yield Static(
                    f"无法读取学习结果：{learned_error}",
                    classes="resource-card blocked",
                )
            elif self._learned_terms:
                yield OptionList(
                    *(
                        Option(
                            f"{term.canonical}"
                            + (
                                f"  ←  {', '.join(term.aliases)}"
                                if term.aliases
                                else ""
                            ),
                            id=f"learned-{index}",
                        )
                        for index, term in enumerate(self._learned_terms)
                    ),
                    id="learned-list",
                )
            else:
                yield Static("暂无待确认学习项。", classes="desk-note")
            with Horizontal(classes="desk-actions"):
                yield Button("查看学习结果", id="open-learned")
                yield Button(
                    "加入选中",
                    id="accept-selected-learned",
                    disabled=not self._learned_terms,
                )
                yield Button(
                    "忽略选中",
                    id="ignore-selected-learned",
                    disabled=not self._learned_terms,
                )
                yield Button("全部加入我的热词", id="accept-learned", variant="primary")
                yield Button("全部忽略", id="ignore-learned")
            yield Button("迁移旧 YAML / JSON…", id="migrate-glossary")
            yield Static("", id="hotword-status", classes="desk-note")
            yield Static(
                "每行一个热词；需要别名时写作：正确词 = 别名1, 别名2",
                classes="desk-note",
            )
        yield Footer(compact=True, show_command_palette=False)

    @on(Button.Pressed, "#open-default")
    def open_default(self) -> None:
        path = Path.home() / ".subtap" / "glossaries" / "default.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        _open_file_cross_platform(path)

    @on(Button.Pressed, "#open-learned")
    def open_learned(self) -> None:
        path = Path.home() / ".subtap" / "glossaries" / "learned.txt"
        if not path.is_file():
            self.notify("尚无自动学习结果。", severity="warning")
            return
        _open_file_cross_platform(path)

    def _refresh_with_status(self, message: str) -> None:
        self.refresh(recompose=True)
        self.call_after_refresh(
            lambda: self.query_one("#hotword-status", Static).update(message)
        )

    @on(Button.Pressed, "#accept-learned")
    def accept_learned(self) -> None:
        root = Path.home() / ".subtap" / "glossaries"
        learned = root / "learned.txt"
        status = self.query_one("#hotword-status", Static)
        try:
            terms = load_glossary(learned).terms
            if not terms:
                status.update("没有待确认的学习项。")
                return
            upsert_plain_glossary_terms(root / "default.txt", terms)
            learned.write_text("", encoding="utf-8")
        except (OSError, ValueError) as error:
            status.update(f"无法加入：{error}")
            return
        self._refresh_with_status(f"✓ 已加入 {len(terms)} 个热词")

    @on(Button.Pressed, "#ignore-learned")
    def ignore_learned(self) -> None:
        path = Path.home() / ".subtap" / "glossaries" / "learned.txt"
        status = self.query_one("#hotword-status", Static)
        try:
            terms = load_glossary(path).terms
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        except (OSError, ValueError) as error:
            status.update(f"无法忽略：{error}")
            return
        self._refresh_with_status(f"✓ 已忽略 {len(terms)} 个学习项")

    def _selected_learned_term(self):
        if not self._learned_terms:
            return None
        option_list = self.query_one("#learned-list", OptionList)
        index = option_list.highlighted
        if index is None:
            return None
        return self._learned_terms[index]

    def _finish_selected_learned(self, *, accept: bool) -> None:
        term = self._selected_learned_term()
        status = self.query_one("#hotword-status", Static)
        if term is None:
            status.update("请选择一个学习项。")
            return
        root = Path.home() / ".subtap" / "glossaries"
        learned = root / "learned.txt"
        try:
            if accept:
                upsert_plain_glossary_terms(root / "default.txt", [term])
            if not remove_plain_glossary_entry(learned, term.canonical):
                raise ValueError(f"未找到学习项：{term.canonical}")
        except (OSError, ValueError) as error:
            status.update(f"无法更新学习项：{error}")
            return
        self._refresh_with_status(
            f"✓ 已{'加入' if accept else '忽略'} {term.canonical}"
        )

    @on(Button.Pressed, "#accept-selected-learned")
    def accept_selected_learned(self) -> None:
        self._finish_selected_learned(accept=True)

    @on(Button.Pressed, "#ignore-selected-learned")
    def ignore_selected_learned(self) -> None:
        self._finish_selected_learned(accept=False)

    @on(Button.Pressed, "#migrate-glossary")
    def migrate_glossary(self) -> None:
        status = self.query_one("#hotword-status", Static)
        try:
            source = choose_file("选择旧 YAML 或 JSON 热词表")
        except RuntimeError as error:
            status.update(f"无法打开选择器：{error}")
            return
        if source is None:
            return
        if source.suffix.casefold() not in {".yaml", ".yml", ".json"}:
            status.update("请选择 .yaml、.yml 或 .json 文件。")
            return
        root = Path.home() / ".subtap" / "glossaries"
        target = root / f"{source.stem}.txt"
        if target.exists():
            target = root / f"{source.stem}-migrated.txt"
        if target.exists():
            status.update(f"迁移目标已存在：{target}")
            return
        try:
            save_glossary(target, load_glossary(source))
        except (OSError, ValueError) as error:
            status.update(f"迁移失败，原文件未修改：{error}")
            return
        status.update(f"✓ 已迁移到 {target}")


class DiscardPreferencesScreen(ModalScreen[bool]):
    """Confirm leaving preferences with unsaved changes."""

    BINDINGS = [Binding("escape", "cancel", "继续编辑", priority=True)]

    def compose(self) -> ComposeResult:
        with Vertical(classes="resource-card"):
            yield Static("偏好设置尚未保存")
            yield Static("放弃这些更改并返回吗？")
            with Horizontal(classes="desk-actions"):
                yield Button("继续编辑", id="continue-preferences")
                yield Button(
                    "放弃更改",
                    id="discard-preferences",
                    variant="warning",
                )

    @on(Button.Pressed, "#continue-preferences")
    def continue_editing(self) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#discard-preferences")
    def discard(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class PreferencesScreen(DeskScreen):
    """Edit the defaults users need during normal transcription."""

    def __init__(self) -> None:
        super().__init__()
        self._saved_values: tuple[object, str, str, object] | None = None

    def compose(self) -> ComposeResult:
        config = load_config(
            Path.home() / ".subtap" / "config.yaml",
            warn_deprecated=False,
        )
        with VerticalScroll(classes="desk-shell"):
            yield PageHeader("偏好设置", "更改新任务使用的默认设置。")
            yield Static("默认转录质量", classes="desk-label")
            yield Select(
                [("快速 · 0.6B", "asr_0.6b"), ("高质量 · 1.7B", "asr_1.7b")],
                value=config.asr.model,
                id="default-model",
            )
            yield Static("字幕目标最大字数", classes="desk-label")
            yield Input(
                str(config.output.max_chars), type="integer", id="default-chars"
            )
            yield Static("默认输出目录", classes="desk-label")
            with Horizontal(classes="resource-row"):
                yield Input(
                    str(getattr(config.output, "directory", "./output")),
                    id="default-output",
                )
                yield Button("选择…", id="choose-default-output")
            yield Static("服务与隐私", classes="desk-label")
            yield Select(
                [
                    ("完全本地 · 音视频与推理不离开本机", "offline"),
                    ("允许远程服务 · 在线 ASR 会上传音频", "online"),
                ],
                value=getattr(config, "mode", "offline"),
                id="default-service-mode",
            )
            yield Static(
                "本地 ASR 不上传音视频；在线 ASR 会上传音频；文本增强只发送文本。",
                classes="desk-note",
            )
            yield Static("", id="preference-status")
            yield Button("保存设置", id="save-preferences", variant="primary")
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        self._saved_values = self._current_values()

    def _current_values(self) -> tuple[object, str, str, object]:
        return (
            self.query_one("#default-model", Select).value,
            self.query_one("#default-chars", Input).value,
            self.query_one("#default-output", Input).value,
            self.query_one("#default-service-mode", Select).value,
        )

    @on(Button.Pressed, "#choose-default-output")
    def choose_default_output(self) -> None:
        selected = choose_folder("选择默认输出目录")
        if selected is not None:
            self.query_one("#default-output", Input).value = str(selected)

    def action_back(self) -> None:
        if self._saved_values != self._current_values():
            self.app.push_screen(DiscardPreferencesScreen(), self._finish_back)
            return
        super().action_back()

    def _finish_back(self, discard: bool | None) -> None:
        if discard:
            self.app.pop_screen()

    @on(Button.Pressed, "#save-preferences")
    def save_preferences(self) -> None:
        status = self.query_one("#preference-status", Static)
        try:
            max_chars = int(self.query_one("#default-chars", Input).value)
        except ValueError:
            status.update("字幕最大字数必须是 10 到 60 的整数")
            return
        if not 10 <= max_chars <= 60:
            status.update("字幕最大字数必须在 10 到 60 之间")
            return
        model = self.query_one("#default-model", Select).value
        if not isinstance(model, str):
            raise RuntimeError("默认模型选项无效")
        output_dir = self.query_one("#default-output", Input).value.strip()
        if not output_dir:
            status.update("默认输出目录不能为空")
            return
        output_path = Path(output_dir).expanduser()
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            status.update(f"输出目录不可用：{error}")
            return
        if not output_path.is_dir() or not os.access(output_path, os.W_OK):
            status.update(f"输出目录不可写：{output_path}")
            return
        service_mode = self.query_one("#default-service-mode", Select).value
        if service_mode not in {"offline", "online"}:
            raise RuntimeError("服务模式选项无效")
        manager = ConfigManager(Path.home() / ".subtap" / "config.yaml")
        try:
            manager.set("asr.model", model)
            manager.set("output.max_chars", max_chars)
            manager.set("output.directory", str(output_path))
            manager.set("mode", service_mode)
            manager.save()
        except (OSError, ValueError) as error:
            status.update(f"保存失败：{error}")
            return
        self._saved_values = self._current_values()
        status.update("✓ 设置已保存")


class SystemCheckScreen(DeskScreen):
    """Human-readable environment checks without raw CLI output."""

    def __init__(self) -> None:
        super().__init__()
        self._state = "not_run"
        self._checks: list[tuple[str, str, str, str]] = []
        self._check_error: str | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="desk-shell"):
            yield PageHeader("环境检查", "确认字幕工作台可以正常运行。")
            if self._state == "not_run":
                yield Static("尚未开始检查。", classes="desk-note")
            elif self._state == "checking":
                yield Static("正在检查环境…", classes="desk-note")
            elif self._check_error is not None:
                yield Static(
                    f"检查器失败\n{self._check_error}",
                    classes="check-card blocked",
                )
                yield Static(
                    "检查未完成；这不代表环境中的具体项目失败。",
                    classes="desk-note",
                )
            else:
                group_order = ["依赖", "模型", "路径与配置", "权限与空间"]
                groups = {
                    group: [check for check in self._checks if check[0] == group]
                    for group in group_order
                }
                ordered_groups = sorted(
                    group_order,
                    key=lambda group: (
                        min(
                            (
                                {"blocked": 0, "warning": 1, "ok": 2}[check[3]]
                                for check in groups[group]
                            ),
                            default=2,
                        ),
                        group_order.index(group),
                    ),
                )
                for group in ordered_groups:
                    yield Static(group, classes="desk-label")
                    for _, label, detail, severity in sorted(
                        groups[group],
                        key=lambda check: {"blocked": 0, "warning": 1, "ok": 2}[
                            check[3]
                        ],
                    ):
                        state_label = {
                            "ok": "✓ 可以使用",
                            "warning": "! 需要处理",
                            "blocked": "× 无法使用",
                        }[severity]
                        yield Static(
                            f"{state_label}  {label}\n{detail}",
                            classes=f"check-card {severity}",
                        )
                severities = {check[3] for check in self._checks}
                yield Static(
                    (
                        "存在阻塞项，请先处理后再转录。"
                        if "blocked" in severities
                        else (
                            "可以使用，但有建议处理的项目。"
                            if "warning" in severities
                            else "全部关键检查通过。"
                        )
                    ),
                    classes="desk-note",
                )
            yield Button(
                "开始检查" if self._state == "not_run" else "重新检查",
                id="rerun-system-check",
                variant="primary",
                disabled=self._state == "checking",
            )
        yield Footer(compact=True, show_command_palette=False)

    def _run_checks(self) -> list[tuple[str, str, str, str]]:
        config_path = Path.home() / ".subtap" / "config.yaml"
        config = None
        if config_path.is_file():
            try:
                config = load_config(config_path, warn_deprecated=False)
            except (OSError, ValueError) as error:
                config_check = (
                    "路径与配置",
                    "配置文件",
                    f"读取失败：{error}",
                    "blocked",
                )
            else:
                config_check = ("路径与配置", "配置文件", "格式有效", "ok")
        else:
            config_check = ("路径与配置", "配置文件", "尚未创建", "blocked")

        if config is None:
            model_check = ("模型", "运行所需模型", "等待有效配置", "blocked")
        else:
            try:
                statuses = ModelRegistry(config).status()
            except (OSError, ValueError, FileNotFoundError) as error:
                model_check = (
                    "模型",
                    "运行所需模型",
                    f"检查失败：{error}",
                    "blocked",
                )
            else:
                missing = [status.name for status in statuses if not status.installed]
                model_check = (
                    "模型",
                    "运行所需模型",
                    "全部可用" if not missing else f"缺少：{', '.join(missing)}",
                    "ok" if not missing else "blocked",
                )

        output_dir = (
            Path(config.output.directory).expanduser()
            if config is not None
            else Path.cwd()
        )
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
        output_probe = output_dir
        while not output_probe.exists() and output_probe != output_probe.parent:
            output_probe = output_probe.parent
        output_writable = (
            output_dir.is_dir() and os.access(output_dir, os.W_OK)
            if output_dir.exists()
            else os.access(output_probe, os.W_OK)
        )
        free_gb = shutil.disk_usage(output_probe).free / (1024**3)
        return [
            (
                "依赖",
                "Apple 芯片",
                platform.machine(),
                "ok" if platform.machine() == "arm64" else "blocked",
            ),
            (
                "依赖",
                "Python",
                sys.version.split()[0],
                "ok" if sys.version_info >= (3, 10) else "blocked",
            ),
            (
                "依赖",
                "音视频处理",
                shutil.which("ffmpeg") or "未找到",
                "ok" if shutil.which("ffmpeg") is not None else "blocked",
            ),
            (
                "依赖",
                "媒体探测",
                shutil.which("ffprobe") or "未找到",
                "ok" if shutil.which("ffprobe") is not None else "blocked",
            ),
            model_check,
            config_check,
            (
                "权限与空间",
                "默认输出目录",
                str(output_dir),
                "ok" if output_writable else "blocked",
            ),
            (
                "权限与空间",
                "可用磁盘空间",
                f"{free_gb:.1f} GB",
                "ok" if free_gb >= 20 else "warning" if free_gb >= 5 else "blocked",
            ),
        ]

    @on(Button.Pressed, "#rerun-system-check")
    def rerun(self) -> None:
        self._state = "checking"
        self._checks = []
        self._check_error = None
        self.refresh(recompose=True)
        self.call_after_refresh(self._finish_check)

    def _finish_check(self) -> None:
        try:
            self._checks = self._run_checks()
        except Exception as error:
            self._check_error = str(error)
            self._state = "check_error"
        else:
            severities = {check[3] for check in self._checks}
            self._state = (
                "blocked"
                if "blocked" in severities
                else "warning" if "warning" in severities else "usable"
            )
        self.refresh(recompose=True)
