"""Textual form for starting a subtitle task."""

from __future__ import annotations

import logging
from pathlib import Path
import subprocess
from typing import Callable

from textual import on
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, Input, Select, Static

from subtap.core.models import asr_mode_for_model
from subtap.schemas.config import load_config
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
    choices = [("使用默认热词表（default.yaml）", "")]
    for path in paths:
        if path.name == "default.yaml":
            continue
        label = (
            "自动学习热词表（learned.yaml）"
            if path.name == "learned.yaml"
            else f"自定义 · {path.name}"
        )
        choices.append((label, str(path)))
    return choices


class RunSetupApp(App[list[str] | None]):
    """Collect per-task options and return the real pipeline command."""

    CSS = """
    Screen { background: #0b0d10; color: #f2f2f2; padding: 2 4; }
    #form { height: 1fr; }
    Static, Select, Input { margin-bottom: 1; }
    Button { margin-right: 2; }
    #status { color: #ffcc66; }
    #hint, .resource-help { color: #8b8b92; }
    """
    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, input_path: Path) -> None:
        super().__init__()
        self.input_path = input_path
        config = load_config(Path.home() / ".subtap" / "config.yaml")
        self.default_mode = asr_mode_for_model(config.asr.model)
        self.default_max_chars = config.output.max_chars
        self._pending_command: list[str] | None = None
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
            yield Static("[b]新建字幕[/b]")
            yield Static(f"文件：{self.input_path}")
            yield Static("质量")
            yield Select(
                [("快速 · 0.6B", "fast"), ("高质量 · 1.7B", "quality")],
                value=self.default_mode,
                id="quality",
            )
            yield Static("热词表")
            yield Select(self._glossary_options, value="", id="glossary")
            yield Static(
                f"位置：{glossary_dir}\n"
                "default.yaml 是你维护的默认热词；learned.yaml 是系统学习结果。",
                id="glossary-help",
                classes="resource-help",
            )
            yield Button("编辑默认热词表", id="edit-default-glossary")
            yield Button("查看自动学习结果", id="view-learned-glossary")
            yield Button("从文件选择热词表…", id="choose-glossary")
            yield Static("参考文稿")
            yield Select(
                self._manuscript_options,
                value="",
                id="manuscript",
            )
            yield Static(
                f"可选。常用文稿可放在：{manuscript_dir}",
                classes="resource-help",
            )
            yield Button("选择参考文稿…", id="choose-manuscript")
            yield Static(
                "字幕目标最大字数（建议 25；范围 10–60；完整英文单词可能超出）",
                id="max-chars-help",
            )
            yield Input(
                value=str(self.default_max_chars),
                type="integer",
                id="max-chars",
            )
            yield Static("输出目录")
            yield Input(value=str(Path.cwd() / "output"), id="output")
            yield Button("选择输出目录…", id="choose-output")
            yield Static("Tab 切换 · Enter 确认 · Esc 取消", id="hint")
            yield Static("", id="status")
            yield Static("", id="confirmation")
            yield Button("检查设置", id="start", variant="primary")
            yield Button("取消", id="cancel")

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
        self._pending_command = None

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

    @on(Button.Pressed, "#choose-glossary")
    def choose_glossary(self) -> None:
        path = self._pick_path(_choose_native_file, "选择本地热词表")
        if path is not None:
            self._set_selected_file("#glossary", self._glossary_options, path, "自定义")

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

    @on(Button.Pressed, "#edit-default-glossary")
    def edit_default_glossary(self) -> None:
        from subtap.core.user_resources import ensure_default_glossary

        self._open_glossary(ensure_default_glossary())

    @on(Button.Pressed, "#view-learned-glossary")
    def view_learned_glossary(self) -> None:
        self._open_glossary(Path.home() / ".subtap" / "glossaries" / "learned.yaml")

    @on(Button.Pressed, "#choose-manuscript")
    def choose_manuscript(self) -> None:
        path = self._pick_path(_choose_native_file, "选择参考文稿")
        if path is not None:
            self._set_selected_file(
                "#manuscript", self._manuscript_options, path, "本地文稿"
            )

    @on(Button.Pressed, "#choose-output")
    def choose_output(self) -> None:
        path = self._pick_path(_choose_native_folder, "选择字幕输出目录")
        if path is not None:
            self.query_one("#output", Input).value = str(path)
            self._pending_command = None

    @on(Button.Pressed, "#start")
    def start(self) -> None:
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
        if command == self._pending_command:
            self.exit(command)
            return
        self._pending_command = command
        self.query_one("#status", Static).update("")
        self.query_one("#confirmation", Static).update(
            "[b]请确认[/b]\n" + "\n".join(wizard.get_confirm_items())
        )
        self.query_one("#start", Button).label = "确认并开始"

    @on(Button.Pressed, "#cancel")
    def cancel_button(self) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.exit(None)
