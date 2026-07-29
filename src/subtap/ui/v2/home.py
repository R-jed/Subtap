"""Signal Desk home screen."""

import os
from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Button, Footer, OptionList, Static
from textual.widgets.option_list import Option

from subtap.core.state_store import StateStore

if TYPE_CHECKING:
    from .app import SubtapV2App

HOME_OPTIONS = (
    ("新建字幕  ·  单个音频或视频生成字幕", "run"),
    ("批量转录  ·  批量处理媒体目录", "batch"),
    ("任务记录  ·  查看运行中与历史任务", "observe"),
    ("模型管理  ·  查看本地模型状态", "models"),
    ("热词管理  ·  维护热词和学习结果", "glossary"),
    ("偏好设置  ·  更改模型与服务配置", "setup"),
    ("环境检查  ·  检查安装和运行环境", "doctor"),
)
HOME_ACTIONS = frozenset(action for _, action in HOME_OPTIONS)

HOME_LOGO = (
    "████████  ██    ██  ████████  ██████████    ██████    ████████\n"
    "██        ██    ██  ██    ██      ██       ██    ██   ██    ██\n"
    "████████  ██    ██  ████████      ██       ████████   ████████\n"
    "      ██  ██    ██  ██    ██      ██       ██    ██   ██      \n"
    "████████    ████    ████████      ██       ██    ██   ██      "
)


def _is_live_task(task: dict) -> bool:
    if task.get("status") != "running":
        return False
    pid = task.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    return False


HOME_CSS = """
HomeScreen {
    align: center top;
}

#home-shell {
    width: 100%;
    max-width: 104;
    height: 1fr;
    padding: 1 2 0 2;
}

#home-logo, #home-logo-compact {
    height: auto;
    color: $primary;
    text-style: bold;
}

#home-logo {
    display: none;
}

HomeScreen.-regular #home-logo,
HomeScreen.-wide #home-logo {
    display: block;
}

HomeScreen.-regular #home-logo-compact,
HomeScreen.-wide #home-logo-compact {
    display: none;
}

#home-tagline {
    height: auto;
    color: $text;
    text-style: bold;
}

#home-capabilities, #home-url, #home-disclosure {
    height: auto;
    color: $text-muted;
}

#home-disclosure {
    margin-bottom: 1;
}

#home-task-status {
    height: auto;
    margin-bottom: 1;
    padding: 1 2;
    background: $surface;
}

#continue-task {
    width: 100%;
    margin-bottom: 1;
}

#recent-tasks {
    width: 100%;
    height: auto;
    margin-bottom: 1;
}

.recent-task {
    width: 1fr;
    min-width: 0;
}

HomeScreen.-compact #recent-tasks {
    layout: vertical;
}

#home-menu {
    height: auto;
    max-height: 8;
}

HomeScreen.-short #home-shell {
    padding-top: 0;
}

"""


class HomeScreen(Screen[None]):
    """Choose the next Subtap task."""

    @staticmethod
    def _task_snapshot(tasks: list[dict]) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                task.get("task_id"),
                task.get("status"),
                task.get("pid"),
                task.get("output_path"),
                _is_live_task(task),
            )
            for task in tasks
        )

    def compose(self) -> ComposeResult:
        tasks = StateStore(Path.home() / ".subtap" / "state.json").load().recent_tasks
        self._tasks_snapshot = self._task_snapshot(tasks)
        running = next(
            (task for task in tasks if _is_live_task(task)),
            None,
        )
        self.running_task_id = (
            str(running.get("task_id")) if running is not None else None
        )
        with Vertical(id="home-shell"):
            yield Static(HOME_LOGO, id="home-logo")
            yield Static("SUBTAP", id="home-logo-compact")
            yield Static("本地优先的字幕生成与转录", id="home-tagline")
            yield Static(
                "音视频转录 · 批量处理 · 热词增强 · 时间轴生成",
                id="home-capabilities",
            )
            yield Static("https://github.com/R-jed/Subtap", id="home-url")
            yield Static(
                "默认在 Apple 芯片本地处理；启用在线 ASR 时音频会上传",
                id="home-disclosure",
            )
            if running is not None:
                yield Static(
                    f"任务进行中 · {running.get('input_name', '未知文件')}",
                    id="home-task-status",
                )
                yield Button("继续观察任务", id="continue-task", variant="primary")
            elif tasks:
                yield Static("最近任务", id="home-task-status")
                with Horizontal(id="recent-tasks"):
                    for task in tasks[:3]:
                        yield Button(
                            str(task.get("input_name", "未知文件")),
                            name=str(task.get("task_id", "")),
                            classes="recent-task",
                        )
            yield OptionList(
                *(Option(label, id=action) for label, action in HOME_OPTIONS),
                id="home-menu",
            )
        yield Footer(compact=True, show_command_palette=False)

    def on_screen_resume(self) -> None:
        tasks = StateStore(Path.home() / ".subtap" / "state.json").load().recent_tasks
        if self._task_snapshot(tasks) != self._tasks_snapshot:
            self.refresh(recompose=True)

    @on(Button.Pressed, "#continue-task")
    def continue_task(self) -> None:
        from .screens import TasksScreen

        app = cast("SubtapV2App", self.app)
        if self.running_task_id is not None and app.resume_observer(
            self.running_task_id
        ):
            return
        self.app.push_screen(TasksScreen(auto_open_task_id=self.running_task_id))

    @on(Button.Pressed, ".recent-task")
    def open_recent_task(self, event: Button.Pressed) -> None:
        from .screens import TasksScreen

        self.app.push_screen(TasksScreen(auto_open_task_id=event.button.name))

    @on(OptionList.OptionSelected)
    def option_selected(self, event: OptionList.OptionSelected) -> None:
        action = event.option.id
        if action not in HOME_ACTIONS:
            raise ValueError(f"Unknown Home action: {action!r}")
        if action == "run":
            from .new_transcription import NewTranscriptionScreen

            self.app.push_screen(NewTranscriptionScreen(), self._finish_transcription)
            return
        from .screens import (
            BatchScreen,
            HotwordsScreen,
            ModelsScreen,
            PreferencesScreen,
            SystemCheckScreen,
            TasksScreen,
        )

        screens = {
            "batch": BatchScreen,
            "observe": TasksScreen,
            "models": ModelsScreen,
            "glossary": HotwordsScreen,
            "setup": PreferencesScreen,
            "doctor": SystemCheckScreen,
        }
        self.app.push_screen(screens[action]())

    def _finish_transcription(self, command: list[str] | None) -> None:
        if command is not None:
            cast("SubtapV2App", self.app).start_transcription(command)

    def on_resize(self, event: Resize) -> None:
        self.set_class(event.size.height < 18, "-short")
