"""Secondary pages used by the Textual command deck."""

from __future__ import annotations

import logging
from pathlib import Path
import subprocess
import sys
from typing import Callable

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, VerticalScroll
from textual.events import Resize
from textual.screen import Screen
from textual.widgets import Button, Static

from subtap.ui.textual_run_setup import _choose_native_file, _choose_native_folder

logger = logging.getLogger(__name__)


class CommandPage(Screen[list[str] | None]):
    """Shared navigation and visual rhythm for a secondary page."""

    CSS = """
    CommandPage {
        background: $background;
        color: $foreground;
        padding: 1 3;
    }
    #page-body { height: 1fr; max-width: 100; }
    #page-title { height: auto; color: $accent; text-style: bold; }
    #page-description, #page-hint { height: auto; color: $text-muted; }
    #page-status { height: auto; color: $warning; }
    #page-actions { height: 3; margin-top: 1; }
    #page-actions Button { width: 1fr; margin-right: 1; }
    #page-actions Button:last-child { margin-right: 0; }
    """
    BINDINGS = [
        ("escape", "back", "返回"),
        ("q", "quit_tool", "退出"),
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
            yield Static("Esc 返回 · Q 退出", id="page-hint")

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
            yield Static("Esc 返回 · Q 退出", id="page-hint")

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
            yield Static("Esc 返回 · Q 退出", id="page-hint")

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
    GlossaryPage.-narrow #glossary-page-actions {
        grid-size: 1 3;
        grid-columns: 1fr;
        grid-rows: 3 3 3;
        height: 11;
    }
    """

    def on_resize(self, event: Resize) -> None:
        self.set_class(event.size.width < 80, "-narrow")

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
            yield Static("Esc 返回 · Q 退出", id="page-hint")

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


def observe_page() -> PickerCommandPage:
    return PickerCommandPage(
        title="观察任务",
        description="选择任务的 run.log.jsonl 查看当前或历史状态。",
        choose_label="选择 run.log.jsonl…",
        prompt="选择 run.log.jsonl",
        chooser=_choose_native_file,
        build_command=lambda path: [
            sys.executable,
            "-m",
            "subtap.cli",
            "observe",
            str(path),
        ],
    )
