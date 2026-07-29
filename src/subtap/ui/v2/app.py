"""Independent Textual composition root for Subtap TUI v2."""

from __future__ import annotations

from pathlib import Path
import os
import subprocess
import uuid

from textual.binding import Binding
from textual.screen import Screen
from textual.timer import Timer

from subtap.core.state_store import StateStore
from subtap.schemas.config import load_config
from subtap.cli.pipeline_cli import (
    _safe_remove_recent_task,
    _stop_observer_child,
)
from subtap.ui.observer import TaskState

from .home import HOME_CSS, HomeScreen
from .observer import ObserverHostApp, ObserverTaskScreen
from .theme import HORIZONTAL_BREAKPOINTS, SIGNAL_DESK_CSS, SIGNAL_DESK_THEME


class SubtapV2App(ObserverHostApp):
    """Signal Desk application shell."""

    TITLE = "subtap"
    ENABLE_COMMAND_PALETTE = False
    HORIZONTAL_BREAKPOINTS = HORIZONTAL_BREAKPOINTS
    CSS = SIGNAL_DESK_CSS + HOME_CSS
    BINDINGS = [
        Binding("escape", "back", "返回"),
        Binding("q", "quit_context", "退出", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._process: subprocess.Popen | None = None
        self._log_path = Path()
        self._output_path: Path | None = None
        self._diagnostic_path: Path | None = None
        self._run_id: str | None = None
        self._interrupted = False
        self._task_screen: ObserverTaskScreen | None = None
        self._observer_timer: Timer | None = None
        self._event_cursor = None
        self._batch_processes: dict[str, subprocess.Popen] = {}
        self._model_process: subprocess.Popen | None = None
        self._model_operation: str | None = None
        self.register_theme(SIGNAL_DESK_THEME)
        self.theme = SIGNAL_DESK_THEME.name

    def get_default_screen(self) -> Screen:
        return HomeScreen()

    def _stop_observer_timer(self) -> None:
        timer = self._observer_timer
        if timer is None:
            return
        timer.stop()
        self._observer_timer = None

    def _start_observer_timer(self) -> None:
        self._stop_observer_timer()
        self._observer_timer = self.set_interval(1.0, self.refresh_from_log)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "back" and len(self.screen_stack) == 1:
            return False
        if action == "interrupt_task":
            return self._process is not None and self._process.poll() is None
        return True

    def start_transcription(self, command: list[str]) -> None:
        """Run the pipeline as a child while this App remains mounted."""
        if self._process is not None and self._process.poll() is None:
            raise RuntimeError("已有字幕任务正在运行")
        flags = {"--tui", "--tui-v2", "--observer-child", "--no-tui"}
        child_command = [part for part in command if part not in flags]
        child_command.extend(["--observer-child", "--no-tui"])
        config = load_config(
            Path.home() / ".subtap" / "config.yaml",
            warn_deprecated=False,
        )
        work_dir = Path(config.workspace.root).expanduser()
        if not work_dir.is_absolute():
            work_dir = Path.cwd() / work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        output_dir = Path(self._command_value(command, "--output-dir", "./output"))
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir
        input_path = Path(command[command.index("run") + 1])
        output_format = self._command_value(command, "--format", "srt")
        run_id = uuid.uuid4().hex
        self._run_id = run_id
        task_dir = work_dir / "jobs" / run_id
        task_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = task_dir / "run.log.jsonl"
        self._output_path = output_dir / f"{input_path.stem}.{output_format}"
        self._diagnostic_path = work_dir / "run_latest.log"
        child_log_path = task_dir / "observer-child.log"
        child_env = {
            **os.environ,
            "SUBTAP_RUN_ID": run_id,
            "SUBTAP_EVENT_LOG": str(self._log_path),
        }
        task_store = StateStore(Path.home() / ".subtap" / "state.json")
        task_store.add_recent_task(
            run_id,
            input_path.name,
            str(self._output_path),
            log_path=str(self._log_path),
            diagnostic_path=str(self._diagnostic_path),
            status="starting",
        )
        process = None
        try:
            with child_log_path.open("w", encoding="utf-8") as child_log:
                process = subprocess.Popen(
                    child_command,
                    start_new_session=True,
                    stdout=child_log,
                    stderr=subprocess.STDOUT,
                    env=child_env,
                )
        finally:
            if process is None:
                _safe_remove_recent_task(run_id)
        self._process = process
        try:
            attached = task_store.attach_recent_task_process(run_id, process.pid)
        except (OSError, ValueError):
            _stop_observer_child(process)
            raise
        if not attached:
            _stop_observer_child(process)
            raise RuntimeError(f"无法关联任务进程，任务不存在：{run_id}")
        self._interrupted = False
        self._task_screen = ObserverTaskScreen(self._build_presentation())
        self.push_screen(self._task_screen)
        self._event_cursor = None
        self._start_observer_timer()

    def register_batch_process(
        self,
        task_id: str,
        process: subprocess.Popen,
    ) -> None:
        """Keep ownership of a live batch while screens are replaced."""
        self._batch_processes[task_id] = process

    def get_batch_process(self, task_id: str) -> subprocess.Popen | None:
        """Return the process owned by this app, pruning completed entries."""
        process = self._batch_processes.get(task_id)
        if process is not None and process.poll() is not None:
            self._batch_processes.pop(task_id, None)
            return None
        return process

    def register_model_process(
        self,
        process: subprocess.Popen,
        operation: str,
    ) -> None:
        """Keep one model operation alive while its screen is replaced."""
        if self._model_process is not None and self._model_process.poll() is None:
            raise RuntimeError("已有模型操作正在运行")
        self._model_process = process
        self._model_operation = operation

    def get_model_process(self) -> tuple[subprocess.Popen, str] | None:
        """Return the current model operation, including a completed result."""
        if self._model_process is None or self._model_operation is None:
            return None
        return self._model_process, self._model_operation

    def clear_model_process(self, process: subprocess.Popen) -> None:
        """Release a model operation after its result has been presented."""
        if self._model_process is process:
            self._model_process = None
            self._model_operation = None

    @staticmethod
    def _command_value(command: list[str], flag: str, default: str) -> str:
        try:
            return command[command.index(flag) + 1]
        except (ValueError, IndexError):
            return default

    def resume_observer(self, task_id: str) -> bool:
        """Resume the live task owned by this app; history stays read-only."""
        if (
            self._run_id != task_id
            or self._process is None
            or self._process.poll() is not None
        ):
            return False
        self._task_screen = ObserverTaskScreen(self._build_presentation())
        self.push_screen(self._task_screen)
        self._start_observer_timer()
        return True

    def action_quit_observer(self) -> None:
        """Detach from the child without stopping the pipeline."""
        from .screens import TasksScreen

        self._stop_observer_timer()
        if len(self.screen_stack) > 1:
            self.pop_screen()
        self._task_screen = None
        if not isinstance(self.screen, TasksScreen):
            self.push_screen(TasksScreen())

    def action_quit_context(self) -> None:
        """Exit the tool, except while explicitly observing a task."""
        from .screens import RecordedTaskScreen

        if (
            isinstance(self.screen, ObserverTaskScreen)
            and self.screen.presentation.state is TaskState.RUNNING
        ):
            self.action_quit_observer()
        elif (
            isinstance(self.screen, RecordedTaskScreen)
            and self.screen.presentation.state is TaskState.RUNNING
        ):
            self.pop_screen()
        else:
            self.exit()

    def on_unmount(self) -> None:
        """Do not leave an untracked model writer behind after app exit."""
        self._stop_observer_timer()
        if self._model_process is not None and self._model_process.poll() is None:
            _stop_observer_child(self._model_process)
        self._model_process = None
        self._model_operation = None
