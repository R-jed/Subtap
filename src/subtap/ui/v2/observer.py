"""Live observer app for Signal Desk task views."""

from __future__ import annotations

from dataclasses import replace
import logging
from pathlib import Path
import subprocess
import time
from typing import Any, cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import Footer, Static

from subtap.cli.hotword_cli import _open_file_cross_platform
from subtap.cli.pipeline_cli import _record_interrupted_task, _stop_observer_child
from subtap.ui.observer import (
    TaskState,
    EventLogCursor,
    _summarize_event_rows,
    build_observation_error_presentation,
    build_task_presentation,
    iter_event_log,
)

from .components import TaskDetails
from .task_views import TaskScreen, TaskView
from .theme import HORIZONTAL_BREAKPOINTS, SIGNAL_DESK_CSS, SIGNAL_DESK_THEME

logger = logging.getLogger(__name__)


class InterruptTaskScreen(ModalScreen[bool]):
    """Require an explicit answer before stopping the pipeline."""

    DEFAULT_CSS = """
    InterruptTaskScreen {
        align: center middle;
        background: $background 70%;
    }
    #interrupt-dialog {
        width: 100%;
        max-width: 58;
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
        yield Static(
            "[b]停止当前任务？[/b]\n\n"
            "这会终止字幕处理；已生成的工作文件会保留。\n\n"
            "按 Y 确认，按 N 或 Esc 返回。",
            id="interrupt-dialog",
        )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_keep_running(self) -> None:
        self.dismiss(False)


class ObserverHostApp(App[Any]):
    """Shared live-observer behavior for standalone and workbench apps."""

    _log_path: Path
    _process: Any
    _output_path: Path | None
    _run_id: str | None
    _diagnostic_path: Path | None
    _interrupted: bool
    _task_screen: ObserverTaskScreen | None
    _observer_timer: Timer | None
    _event_cursor: EventLogCursor | None

    def _build_presentation(self):
        try:
            if self._event_cursor is None:
                self._event_cursor = EventLogCursor(self._log_path, recent_limit=12)
                self._event_cursor.read_initial()
            else:
                self._event_cursor.read_updates()
            state = self._event_cursor.state
        except ValueError as error:
            logger.exception("任务观察日志无效：%s", self._log_path)
            previous = (
                self._task_screen.presentation
                if self._task_screen is not None
                else None
            )
            return build_observation_error_presentation(error, previous)
        presentation = build_task_presentation(
            state,
            returncode=self._process.poll(),
            output_path=self._output_path,
            now=time.time(),
        )
        return (
            replace(
                presentation,
                status="任务已中断",
                state=TaskState.INTERRUPTED,
            )
            if self._interrupted
            else presentation
        )

    def _stop_observer_timer(self) -> None:
        timer = self._observer_timer
        if timer is None:
            return
        timer.stop()
        self._observer_timer = None

    def _start_observer_timer(self) -> None:
        self._stop_observer_timer()
        self._observer_timer = self.set_interval(1.0, self.refresh_from_log)

    async def refresh_from_log(self) -> None:
        if self._task_screen is None:
            raise RuntimeError("Observer task screen is not mounted")
        previous = self._task_screen.presentation
        presentation = self._build_presentation()
        await self._task_screen.update_presentation(presentation)
        if previous.allowed_actions != presentation.allowed_actions:
            self.refresh_bindings()
        if presentation.state is not TaskState.RUNNING:
            self._stop_observer_timer()

    def action_interrupt_task(self) -> None:
        if self._process.poll() is None:
            self.push_screen(InterruptTaskScreen(), self._finish_interrupt)

    def _finish_interrupt(self, confirmed: bool | None) -> None:
        if confirmed and self._process.poll() is None:
            _stop_observer_child(self._process)
            state = _summarize_event_rows(iter_event_log(self._log_path))
            if state.get("pipeline_status") != "interrupted":
                task_id = state.get("run_id") or self._run_id
                if task_id is None:
                    raise RuntimeError("无法记录中断状态：任务标识缺失")
                started_at = state.get("started_at")
                _record_interrupted_task(
                    self._log_path,
                    task_id,
                    total_duration_sec=(
                        max(0.0, time.time() - float(started_at))
                        if started_at is not None
                        else 0.0
                    ),
                )
            self._interrupted = True
            self.call_after_refresh(self.refresh_from_log)
        elif confirmed:
            self.call_after_refresh(self.refresh_from_log)

    def _open_path(self, target: Path, label: str) -> None:
        try:
            _open_file_cross_platform(target)
        except (OSError, subprocess.SubprocessError) as error:
            logger.exception("打开%s失败：%s", label, target)
            self.notify(f"打开{label}失败：{error}", severity="error")
            return
        self.notify(f"已打开{label}。")

    def _has_output(self) -> bool:
        return (
            self._process.poll() == 0
            and self._output_path is not None
            and self._output_path.is_file()
        )

    def action_open_output_directory(self) -> None:
        if not self._has_output():
            self.notify("没有可打开的字幕结果。", severity="warning")
            return
        assert self._output_path is not None
        self._open_path(self._output_path.parent, "输出目录")

    def action_open_output_file(self) -> None:
        if not self._has_output():
            self.notify("没有可打开的字幕结果。", severity="warning")
            return
        assert self._output_path is not None
        self._open_path(self._output_path, "字幕")

    def action_open_diagnostics(self) -> None:
        diagnostic_path = self._diagnostic_path
        if self._process.poll() is None:
            self.notify("任务结束后才能打开诊断日志。", severity="warning")
        elif diagnostic_path is None or not diagnostic_path.is_file():
            self.notify(f"未找到诊断日志：{diagnostic_path}", severity="warning")
        else:
            self._open_path(diagnostic_path, "诊断日志")

    def action_quit_observer(self) -> None:
        raise NotImplementedError


class ObserverTaskScreen(TaskScreen):
    """Task screen with live-process controls."""

    BINDINGS = [
        Binding("q", "quit_observer", "退出观察", priority=True),
        ("x", "interrupt_task", "停止任务"),
        ("o", "open_output_file", "打开字幕"),
        ("f", "open_output_directory", "输出目录"),
        ("d", "open_diagnostics", "诊断日志"),
        ("n", "new_task", "新建任务"),
        ("escape", "show_overview", "返回概览"),
    ]

    def compose(self) -> ComposeResult:
        yield TaskView(self.presentation)
        yield Footer(compact=True, show_command_palette=False)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        app = cast(ObserverHostApp, self.app)
        if action == "interrupt_task":
            return app._process.poll() is None
        if action in {"open_output_file", "open_output_directory"}:
            return app._has_output()
        if action == "open_diagnostics":
            return (
                app._process.poll() is not None
                and app._diagnostic_path is not None
                and app._diagnostic_path.is_file()
            )
        if action == "new_task":
            return "new_task" in self.presentation.allowed_actions
        return True

    def action_quit_observer(self) -> None:
        cast(ObserverHostApp, self.app).action_quit_observer()

    def action_interrupt_task(self) -> None:
        cast(ObserverHostApp, self.app).action_interrupt_task()

    def action_open_output_directory(self) -> None:
        cast(ObserverHostApp, self.app).action_open_output_directory()

    def action_open_output_file(self) -> None:
        cast(ObserverHostApp, self.app).action_open_output_file()

    def action_open_diagnostics(self) -> None:
        cast(ObserverHostApp, self.app).action_open_diagnostics()

    def action_show_overview(self) -> None:
        details = self.query_one(TaskDetails)
        if not details.collapsed:
            details.collapsed = True
        else:
            cast(ObserverHostApp, self.app).action_quit_observer()


class V2ObserverApp(ObserverHostApp):
    """Read pipeline events and refresh one Signal Desk task screen."""

    TITLE = "subtap"
    ENABLE_COMMAND_PALETTE = False
    HORIZONTAL_BREAKPOINTS = HORIZONTAL_BREAKPOINTS
    CSS = SIGNAL_DESK_CSS
    BINDINGS = [
        Binding("q", "quit_observer", "退出观察", priority=True),
        ("x", "interrupt_task", "停止任务"),
    ]

    def __init__(
        self,
        log_path: Path,
        process,
        *,
        refresh_interval: float = 1.0,
        output_path: Path | None = None,
        run_id: str | None = None,
        diagnostic_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._log_path = log_path
        self._process = process
        self._refresh_interval = refresh_interval
        self._output_path = output_path
        self._run_id = run_id
        self._diagnostic_path = diagnostic_path
        self._interrupted = False
        self._task_screen: ObserverTaskScreen | None = None
        self._event_cursor = None
        self.register_theme(SIGNAL_DESK_THEME)
        self.theme = SIGNAL_DESK_THEME.name

    def get_default_screen(self) -> Screen:
        self._task_screen = ObserverTaskScreen(self._build_presentation())
        return self._task_screen

    def on_mount(self) -> None:
        self._observer_timer = self.set_interval(
            self._refresh_interval, self.refresh_from_log
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "interrupt_task":
            return self._process.poll() is None
        return True

    def action_quit_observer(self) -> None:
        self.exit("interrupt" if self._interrupted else "quit")


def _make_v2_observer_dashboard(
    log_path: Path,
    process,
    refresh_interval: float = 1.0,
    output_path: Path | None = None,
    run_id: str | None = None,
    diagnostic_path: Path | None = None,
) -> V2ObserverApp:
    """Create the Signal Desk observer app."""
    return V2ObserverApp(
        log_path,
        process,
        refresh_interval=refresh_interval,
        output_path=output_path,
        run_id=run_id,
        diagnostic_path=diagnostic_path,
    )
