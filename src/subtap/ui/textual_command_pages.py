"""Secondary pages used by the Textual command deck."""

from __future__ import annotations

import logging
from pathlib import Path
import subprocess
import sys
from typing import Callable

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, ProgressBar, Static

from subtap.ui.native_picker import (
    choose_file as _choose_native_file,
    choose_folder as _choose_native_folder,
)
from subtap.ui.theme import CALM_WORKBENCH_BREAKPOINTS, CALM_WORKBENCH_CSS

logger = logging.getLogger(__name__)


class CommandPage(Screen[list[str] | None]):
    """Shared navigation and visual rhythm for a secondary page."""

    HORIZONTAL_BREAKPOINTS = CALM_WORKBENCH_BREAKPOINTS
    CSS = CALM_WORKBENCH_CSS + """
    CommandPage {
        align: center top;
    }
    #page-body {
        width: 100%;
        max-width: 104;
        height: 1fr;
        padding: 1 3 0 3;
    }
    #page-title { height: auto; color: $accent; text-style: bold; }
    #page-description { height: auto; color: $text-muted; }
    #page-status { height: auto; color: $warning; }
    #page-actions { height: 3; margin-top: 1; }
    #page-actions Button { width: 1fr; margin-right: 1; }
    #page-actions Button:last-child { margin-right: 0; }
    #observe-progress { margin: 1 0; }
    #observe-layout {
        grid-size: 2 1;
        grid-columns: 2fr 3fr;
        grid-gutter: 1 2;
        height: auto;
    }
    #observe-pipeline-pane, #observe-activity-pane {
        height: auto;
        padding: 1 2;
        background: $surface;
    }
    CommandPage.-compact #observe-layout {
        grid-size: 1 2;
        grid-columns: 1fr;
    }
    """
    BINDINGS = [
        Binding("escape", "back", "返回"),
        Binding("q", "quit_tool", "退出", priority=True),
    ]

    def action_back(self) -> None:
        self.dismiss(None)

    def action_quit_tool(self) -> None:
        self.app.exit(None)


class PickerCommandPage(CommandPage):
    """Choose a path inside the page before starting a CLI workflow."""

    def __init__(
        self,
        *,
        title: str,
        description: str,
        choose_label: str,
        prompt: str,
        chooser: Callable[[str], Path | None],
        build_command: Callable[[Path], list[str]],
    ) -> None:
        super().__init__()
        self.title_text = title
        self.description = description
        self.choose_label = choose_label
        self.prompt = prompt
        self.chooser = chooser
        self.build_command = build_command
        self.selected_path: Path | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="page-body"):
            yield Static(self.title_text, id="page-title")
            yield Static(self.description, id="page-description")
            yield Static("尚未选择", id="selected-path")
            with Horizontal(id="page-actions"):
                yield Button(self.choose_label, id="choose-path")
                yield Button("开始", id="start-path-command", variant="primary")
                yield Button("返回", id="back")
            yield Static("", id="page-status")
        yield Footer()

    @on(Button.Pressed, "#choose-path")
    def choose_path(self) -> None:
        try:
            selected = self.chooser(self.prompt)
        except RuntimeError as error:
            logger.exception("无法打开系统选择器：%s", self.prompt)
            self.query_one("#page-status", Static).update(
                f"无法打开系统选择器：{error}"
            )
            return
        if selected is not None:
            self.selected_path = selected
            self.query_one("#selected-path", Static).update(str(selected))
            self.query_one("#page-status", Static).update("")

    @on(Button.Pressed, "#start-path-command")
    def start_command(self) -> None:
        if self.selected_path is None:
            self.query_one("#page-status", Static).update("请先选择路径")
            return
        self.dismiss(self.build_command(self.selected_path))

    @on(Button.Pressed, "#back")
    def back_button(self) -> None:
        self.action_back()


class LaunchCommandPage(CommandPage):
    """Explain a workflow before handing it to its existing CLI UI."""

    def __init__(self, title: str, description: str, command: list[str]) -> None:
        super().__init__()
        self.title_text = title
        self.description = description
        self.command = command

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="page-body"):
            yield Static(self.title_text, id="page-title")
            yield Static(self.description, id="page-description")
            with Horizontal(id="page-actions"):
                yield Button("打开", id="launch-command", variant="primary")
                yield Button("返回", id="back")
        yield Footer()

    @on(Button.Pressed, "#launch-command")
    def launch(self) -> None:
        self.dismiss(self.command)

    @on(Button.Pressed, "#back")
    def back_button(self) -> None:
        self.action_back()


class CommandOutputPage(CommandPage):
    """Run a read-only command and keep its result inside the TUI."""

    def __init__(self, title: str, description: str, command: list[str]) -> None:
        super().__init__()
        self.title_text = title
        self.description = description
        self.command = command

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="page-body"):
            yield Static(self.title_text, id="page-title")
            yield Static(self.description, id="page-description")
            yield Static("正在读取…", id="command-output", markup=False)
            yield Static("", id="page-status")
            with Horizontal(id="page-actions"):
                yield Button("重新读取", id="reload-command")
                yield Button("返回", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self.load_output()

    @work(thread=True)
    def load_output(self) -> None:
        try:
            result = subprocess.run(
                self.command,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            logger.exception("命令启动失败：%s", self.command)
            self.app.call_from_thread(self._show_error, str(error))
            return
        output = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )
        self.app.call_from_thread(
            self._show_output,
            output or "没有输出",
            result.returncode,
        )

    def _show_output(self, output: str, returncode: int) -> None:
        self.query_one("#command-output", Static).update(output)
        status = "" if returncode == 0 else f"命令失败（退出码 {returncode}）"
        self.query_one("#page-status", Static).update(status)

    def _show_error(self, error: str) -> None:
        self.query_one("#command-output", Static).update("无法读取")
        self.query_one("#page-status", Static).update(error)

    @on(Button.Pressed, "#reload-command")
    def reload(self) -> None:
        self.query_one("#command-output", Static).update("正在读取…")
        self.query_one("#page-status", Static).update("")
        self.load_output()

    @on(Button.Pressed, "#back")
    def back_button(self) -> None:
        self.action_back()


class GlossaryPage(CommandPage):
    """Open user-owned glossary resources without leaving the page."""

    CSS = """
    #glossary-page-actions {
        grid-size: 3 1;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 3;
        grid-gutter: 1;
        height: 3;
        margin-top: 1;
    }
    #glossary-page-actions Button { width: 100%; }
    GlossaryPage.-compact #glossary-page-actions {
        grid-size: 1 3;
        grid-columns: 1fr;
        grid-rows: 3 3 3;
        height: 11;
    }
    """

    def compose(self) -> ComposeResult:
        glossary_dir = Path.home() / ".subtap" / "glossaries"
        with VerticalScroll(id="page-body"):
            yield Static("热词表", id="page-title")
            yield Static(
                "维护 default.txt，查看 learned.txt，或打开热词表目录。",
                id="page-description",
            )
            yield Static(str(glossary_dir), id="selected-path")
            with Grid(id="glossary-page-actions"):
                yield Button("编辑默认热词表", id="edit-default")
                yield Button("查看学习结果", id="view-learned")
                yield Button("打开热词表目录", id="open-glossary-dir")
            yield Static("", id="page-status")
        yield Footer()

    def _open(self, path: Path) -> None:
        try:
            from subtap.cli.hotword_cli import _open_file_cross_platform

            _open_file_cross_platform(path)
        except (OSError, subprocess.SubprocessError) as error:
            logger.exception("无法打开热词资源：%s", path)
            self.query_one("#page-status", Static).update(f"无法打开：{error}")
            return
        self.query_one("#page-status", Static).update(f"已打开：{path.name}")

    @on(Button.Pressed, "#edit-default")
    def edit_default(self) -> None:
        from subtap.core.user_resources import ensure_default_glossary

        self._open(ensure_default_glossary())

    @on(Button.Pressed, "#view-learned")
    def view_learned(self) -> None:
        from subtap.core.user_resources import ensure_learned_glossary

        path = ensure_learned_glossary()
        if path.is_file():
            self._open(path)
        else:
            self.query_one("#page-status", Static).update("暂无自动学习结果")

    @on(Button.Pressed, "#open-glossary-dir")
    def open_directory(self) -> None:
        from subtap.core.user_resources import ensure_default_glossary

        self._open(ensure_default_glossary().parent)


class ObservePage(CommandPage):
    """Observe one current or historical run log without leaving the app."""

    def __init__(self) -> None:
        super().__init__()
        self.log_path: Path | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="page-body"):
            yield Static("观察任务", id="page-title")
            yield Static(
                "选择任务的 run.log.jsonl；当前任务会自动刷新。",
                id="page-description",
            )
            yield Static("尚未选择", id="selected-path")
            yield Static("", id="observe-status")
            yield ProgressBar(
                total=100,
                show_eta=False,
                id="observe-progress",
            )
            with Grid(id="observe-layout"):
                with Vertical(id="observe-pipeline-pane"):
                    yield Static("", id="observe-stage-map")
                with Vertical(id="observe-activity-pane"):
                    yield Static("", id="observe-recent")
                    yield Static("", id="observe-result")
            with Horizontal(id="page-actions"):
                yield Button("选择 run.log.jsonl…", id="choose-observe-log")
                yield Button("重新读取", id="reload-observe-log")
                yield Button("返回", id="back")
            yield Static("", id="page-status")
        yield Footer()

    @on(Button.Pressed, "#choose-observe-log")
    def choose_log(self) -> None:
        try:
            selected = _choose_native_file("选择 run.log.jsonl")
        except RuntimeError as error:
            logger.exception("无法打开任务日志选择器")
            self.query_one("#page-status", Static).update(
                f"无法打开系统选择器：{error}"
            )
            return
        if selected is not None:
            self.log_path = selected
            self.query_one("#selected-path", Static).update(str(selected))
            self.refresh_log()

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh_log)

    def refresh_log(self) -> None:
        if self.log_path is None:
            return
        from subtap.ui.observer import (
            build_task_presentation,
            build_task_status_text,
            summarize_event_log,
        )

        state = summarize_event_log(self.log_path)
        presentation = build_task_presentation(state)
        self.query_one("#observe-status", Static).update(
            build_task_status_text(presentation)
        )
        progress = self.query_one("#observe-progress", ProgressBar)
        if presentation.progress is None:
            progress.update(total=None)
        else:
            progress.update(total=100, progress=presentation.progress)
        self.query_one("#observe-stage-map", Static).update(
            "[b]处理流程[/b]\n" + "\n".join(presentation.stage_lines)
        )
        recent = "\n".join(f"  {text}" for text in presentation.recent_texts)
        self.query_one("#observe-recent", Static).update(
            f"[b]最近字幕[/b]\n{recent or '  暂无'}"
        )
        self.query_one("#observe-result", Static).update(presentation.output_text)
        self.query_one("#page-status", Static).update("")

    @on(Button.Pressed, "#reload-observe-log")
    def reload(self) -> None:
        if self.log_path is None:
            self.query_one("#page-status", Static).update("请先选择 run.log.jsonl")
            return
        self.refresh_log()

    @on(Button.Pressed, "#back")
    def back_button(self) -> None:
        self.action_back()


def batch_page() -> PickerCommandPage:
    return PickerCommandPage(
        title="批量转录",
        description="选择包含媒体文件的目录；取消选择不会退出页面。",
        choose_label="选择媒体文件夹…",
        prompt="选择媒体文件夹",
        chooser=_choose_native_folder,
        build_command=lambda path: [
            sys.executable,
            "-m",
            "subtap.cli",
            "batch-transcribe",
            "--dir",
            str(path),
        ],
    )


def observe_page() -> ObservePage:
    return ObservePage()
