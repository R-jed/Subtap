"""Textual form for starting a subtitle task."""

from __future__ import annotations

import logging
from pathlib import Path
import subprocess
from typing import Any, Callable, ClassVar, TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, Select, Static

from subtap.core.models import asr_mode_for_model
from subtap.schemas.config import load_config
from subtap.ui.theme import CALM_WORKBENCH_BREAKPOINTS, CALM_WORKBENCH_CSS
from subtap.ui.views.wizard import WizardView

logger = logging.getLogger(__name__)


def _run_native_picker(script: str) -> Path | None:
    """Run a macOS picker and distinguish cancellation from picker failure."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        selected = result.stdout.strip()
        return Path(selected) if selected else None
    if "(-128)" in result.stderr or "User canceled" in result.stderr:
        return None
    raise RuntimeError(result.stderr.strip() or "系统文件选择器启动失败")


def _choose_native_file(prompt: str) -> Path | None:
    escaped = prompt.replace("\\", "\\\\").replace('"', '\\"')
    return _run_native_picker(f'POSIX path of (choose file with prompt "{escaped}")')


def _choose_native_folder(prompt: str) -> Path | None:
    escaped = prompt.replace("\\", "\\\\").replace('"', '\\"')
    return _run_native_picker(f'POSIX path of (choose folder with prompt "{escaped}")')


def _glossary_choices(paths: list[Path]) -> list[tuple[str, str]]:
    choices = [("使用默认热词表（default.txt）", "")]
    for path in paths:
        if path.name == "default.txt":
            continue
        label = (
            "自动学习热词表（learned.txt）"
            if path.name == "learned.txt"
            else f"自定义 · {path.name}"
        )
        choices.append((label, str(path)))
    return choices


class ReviewTaskScreen(ModalScreen[bool]):
    """Show the final task settings before starting transcription."""

    CSS = """
    ReviewTaskScreen {
        align: center middle;
        background: $background 70%;
    }
    #review-dialog {
        width: 64;
        max-width: 92%;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $accent;
    }
    #review-title { text-style: bold; color: $accent; }
    #review-summary { height: auto; margin: 1 0; }
    #review-actions { height: 3; }
    #review-actions Button { width: 1fr; margin-right: 1; }
    #review-actions Button:last-child { margin-right: 0; }
    """
    BINDINGS = [
        Binding("y", "confirm", "开始转录"),
        Binding("n", "cancel", "返回修改"),
        Binding("escape", "cancel", "返回修改"),
    ]

    def __init__(self, confirm_items: list[str]) -> None:
        super().__init__()
        self.confirm_items = confirm_items

    def compose(self) -> ComposeResult:
        with Vertical(id="review-dialog"):
            yield Static("复核任务", id="review-title")
            yield Static("\n".join(self.confirm_items), id="review-summary")
            with Horizontal(id="review-actions"):
                yield Button("返回修改", id="review-back")
                yield Button("开始转录", id="confirm-start", variant="primary")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-start":
            self.action_confirm()
        elif event.button.id == "review-back":
            self.action_cancel()
        else:
            raise RuntimeError(f"任务复核未处理按钮：{event.button.id}")


class _RunSetupForm:
    """Collect per-task options and return the real pipeline command."""

    HORIZONTAL_BREAKPOINTS: ClassVar[list[tuple[int, str]] | None] = (
        CALM_WORKBENCH_BREAKPOINTS
    )
    CSS = CALM_WORKBENCH_CSS + """
    Screen {
        align: center top;
    }
    #form {
        width: 100%;
        max-width: 104;
        height: 1fr;
        padding: 1 3 0 3;
    }
    .section-label { color: $accent; text-style: bold; margin-top: 1; }
    Select, Input { margin-bottom: 1; }
    #input-row, #manuscript-row, #output-row, #footer-actions {
        height: 3;
        margin-bottom: 1;
    }
    #manuscript-row Select, #output-row Input { width: 1fr; }
    #choose-manuscript, #choose-output { width: 24; }
    #input-path { width: 1fr; padding: 1 1; color: $foreground; }
    #choose-input { width: 16; }
    #glossary-actions {
        grid-size: 3 1;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 3;
        grid-gutter: 1;
        height: 3;
        margin-bottom: 1;
    }
    #glossary-actions Button { width: 100%; }
    .-compact #glossary-actions {
        grid-size: 1 3;
        grid-columns: 1fr;
        grid-rows: 3 3 3;
        height: 11;
    }
    #footer-actions Button { width: 1fr; margin-right: 1; }
    #footer-actions Button:last-child { margin-right: 0; }
    #status { color: $warning; }
    .resource-help { color: $text-muted; }
    """
    if TYPE_CHECKING:
        app: App[Any]

        def query_one(self, *args: Any, **kwargs: Any) -> Any: ...

        def action_cancel(self) -> None: ...

        def _complete(self, command: list[str]) -> None: ...

    def __init__(self, input_path: Path | None = None) -> None:
        super().__init__()
        self.input_path = input_path
        config = load_config(Path.home() / ".subtap" / "config.yaml")
        self.default_mode = asr_mode_for_model(config.asr.model)
        self.default_max_chars = config.output.max_chars
        self._glossary_options = _glossary_choices(WizardView.list_glossaries())
        self._manuscript_options = [
            ("不使用参考文稿", ""),
            *[
                (f"本地文稿 · {path.name}", str(path))
                for path in WizardView.list_manuscripts()
            ],
        ]

    def compose(self) -> ComposeResult:
        glossary_dir = Path.home() / ".subtap" / "glossaries"
        manuscript_dir = Path.home() / ".subtap" / "manuscripts"
        with VerticalScroll(id="form"):
            yield Static("[b]新建字幕[/b]\n选择媒体并设置字幕参数。")
            yield Static("媒体文件", classes="section-label")
            with Horizontal(id="input-row"):
                yield Static(
                    str(self.input_path) if self.input_path else "尚未选择",
                    id="input-path",
                )
                yield Button("选择文件…", id="choose-input")
            yield Static("质量", classes="section-label")
            yield Select(
                [("快速 · 0.6B", "fast"), ("高质量 · 1.7B", "quality")],
                value=self.default_mode,
                id="quality",
            )
            yield Static("热词表", classes="section-label")
            yield Select(self._glossary_options, value="", id="glossary")
            yield Static(
                f"位置：{glossary_dir}\n"
                "default.txt 由你维护；learned.txt 由系统更新，"
                "手动修改可能被覆盖。",
                id="glossary-help",
                classes="resource-help",
            )
            with Grid(id="glossary-actions"):
                yield Button("编辑默认热词表", id="edit-default-glossary")
                yield Button("查看自动学习结果", id="view-learned-glossary")
                yield Button("选择其他热词表…", id="choose-glossary")
            yield Static("参考文稿", classes="section-label")
            with Horizontal(id="manuscript-row"):
                yield Select(
                    self._manuscript_options,
                    value="",
                    id="manuscript",
                )
                yield Button("选择参考文稿…", id="choose-manuscript")
            yield Static(
                f"可选。常用文稿可放在：{manuscript_dir}",
                classes="resource-help",
            )
            yield Static(
                "字幕目标最大字数（建议 25；范围 10–60；完整英文单词可能超出）",
                id="max-chars-help",
            )
            yield Input(
                value=str(self.default_max_chars),
                type="integer",
                id="max-chars",
            )
            yield Static("输出目录", classes="section-label")
            with Horizontal(id="output-row"):
                yield Input(value=str(Path.cwd() / "output"), id="output")
                yield Button("选择输出目录…", id="choose-output")
            yield Static("", id="status")
            with Horizontal(id="footer-actions"):
                yield Button("检查设置", id="start", variant="primary")
                yield Button("返回", id="cancel")
        yield Footer()

    def _set_selected_file(
        self,
        select_id: str,
        options: list[tuple[str, str]],
        path: Path,
        label: str,
    ) -> None:
        value = str(path)
        if all(option_value != value for _, option_value in options):
            options.append((f"{label} · {path.name}", value))
        select = self.query_one(select_id, Select)
        select.set_options(options)
        select.value = value

    def _pick_path(
        self,
        chooser: Callable[[str], Path | None],
        prompt: str,
    ) -> Path | None:
        try:
            return chooser(prompt)
        except RuntimeError as error:
            logger.exception("无法打开系统选择器：%s", prompt)
            self.query_one("#status", Static).update(f"无法打开系统选择器：{error}")
            return None

    def choose_glossary(self) -> None:
        path = self._pick_path(_choose_native_file, "选择本地热词表")
        if path is not None:
            self._set_selected_file("#glossary", self._glossary_options, path, "自定义")

    def choose_input(self) -> None:
        path = self._pick_path(_choose_native_file, "选择音频或视频文件")
        if path is not None:
            self.input_path = path
            self.query_one("#input-path", Static).update(str(path))

    def _open_glossary(self, path: Path) -> None:
        if not path.is_file():
            self.query_one("#status", Static).update("暂无自动学习结果")
            return
        try:
            from subtap.cli.hotword_cli import _open_file_cross_platform

            _open_file_cross_platform(path)
        except (OSError, subprocess.SubprocessError) as error:
            logger.exception("无法打开热词表：%s", path)
            self.query_one("#status", Static).update(f"无法打开热词表：{error}")
            return
        self.query_one("#status", Static).update(f"已打开：{path.name}")

    def edit_default_glossary(self) -> None:
        from subtap.core.user_resources import ensure_default_glossary

        self._open_glossary(ensure_default_glossary())

    def view_learned_glossary(self) -> None:
        from subtap.core.user_resources import ensure_learned_glossary

        self._open_glossary(ensure_learned_glossary())

    def choose_manuscript(self) -> None:
        path = self._pick_path(_choose_native_file, "选择参考文稿")
        if path is not None:
            self._set_selected_file(
                "#manuscript", self._manuscript_options, path, "本地文稿"
            )

    def choose_output(self) -> None:
        path = self._pick_path(_choose_native_folder, "选择字幕输出目录")
        if path is not None:
            self.query_one("#output", Input).value = str(path)

    def start(self) -> None:
        if self.input_path is None:
            self.query_one("#status", Static).update("请选择音频或视频文件")
            return
        output = self.query_one("#output", Input).value.strip()
        if not output:
            self.query_one("#status", Static).update("请选择输出目录")
            return
        try:
            max_chars = int(self.query_one("#max-chars", Input).value)
        except ValueError:
            self.query_one("#status", Static).update(
                "字幕最大字数必须是 10 到 60 的整数"
            )
            return
        if not 10 <= max_chars <= 60:
            self.query_one("#status", Static).update("字幕最大字数必须在 10 到 60 之间")
            return

        wizard = WizardView()
        wizard.select_file(self.input_path)
        quality = self.query_one("#quality", Select).value
        wizard.select_quality(
            quality if isinstance(quality, str) else self.default_mode
        )
        glossary = self.query_one("#glossary", Select).value
        manuscript = self.query_one("#manuscript", Select).value
        wizard.select_glossary(
            Path(glossary) if isinstance(glossary, str) and glossary else None
        )
        wizard.select_manuscript(
            Path(manuscript) if isinstance(manuscript, str) and manuscript else None
        )
        wizard.select_output_dir(Path(output).expanduser())
        wizard.select_max_chars(max_chars)
        try:
            command = wizard.build_run_command()
        except ValueError as error:
            self.query_one("#status", Static).update(str(error))
            return
        self.query_one("#status", Static).update("")
        self.app.push_screen(
            ReviewTaskScreen(wizard.get_confirm_items()),
            lambda confirmed: self._complete(command) if confirmed else None,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "choose-input": self.choose_input,
            "choose-glossary": self.choose_glossary,
            "edit-default-glossary": self.edit_default_glossary,
            "view-learned-glossary": self.view_learned_glossary,
            "choose-manuscript": self.choose_manuscript,
            "choose-output": self.choose_output,
            "start": self.start,
            "cancel": self.action_cancel,
        }
        button_id = event.button.id
        if button_id is None:
            raise RuntimeError("Run Setup 按钮缺少 id")
        try:
            handler = handlers[button_id]
        except KeyError as error:
            raise RuntimeError(f"Run Setup 未处理按钮：{button_id}") from error
        handler()


class RunSetupScreen(_RunSetupForm, Screen[list[str] | None]):
    """Setup page hosted by the main Command Deck app."""

    BINDINGS = [
        Binding("escape", "cancel", "返回"),
        Binding("q", "app.quit", "退出", priority=True),
    ]
    compose = _RunSetupForm.compose

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _complete(self, command: list[str]) -> None:
        self.dismiss(command)


class RunSetupApp(_RunSetupForm, App[list[str] | None]):
    """Compatibility entry point for tests and direct setup use."""

    BINDINGS = [
        Binding("escape", "cancel", "返回"),
        Binding("q", "quit", "退出", priority=True),
    ]
    compose = _RunSetupForm.compose

    def action_cancel(self) -> None:
        self.exit(None)

    def _complete(self, command: list[str]) -> None:
        self.exit(command)
