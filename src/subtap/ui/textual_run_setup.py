"""Textual form for starting a subtitle task."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button, Input, Select, Static

from subtap.core.models import asr_mode_for_model
from subtap.schemas.config import load_config
from subtap.ui.views.wizard import WizardView


class RunSetupApp(App[list[str] | None]):
    """Collect per-task options and return the real pipeline command."""

    CSS = """
    Screen { background: #0b0d10; color: #f2f2f2; padding: 2 4; }
    #form { height: 1fr; }
    Static, Select, Input { margin-bottom: 1; }
    Button { margin-right: 2; }
    #status { color: #ffcc66; }
    #hint { color: #8b8b92; }
    """
    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, input_path: Path) -> None:
        super().__init__()
        self.input_path = input_path
        config = load_config(Path.home() / ".subtap" / "config.yaml")
        self.default_mode = asr_mode_for_model(config.asr.model)
        self.default_max_chars = config.output.max_chars
        self._pending_command: list[str] | None = None

    def compose(self) -> ComposeResult:
        glossaries = [(path.name, str(path)) for path in WizardView.list_glossaries()]
        manuscripts = [(path.name, str(path)) for path in WizardView.list_manuscripts()]
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
            yield Select([("使用默认热词表", ""), *glossaries], value="", id="glossary")
            yield Static("参考文稿")
            yield Select(
                [("不使用参考文稿", ""), *manuscripts],
                value="",
                id="manuscript",
            )
            yield Static("字幕目标最大字数（10–60，完整英文单词可能超出）")
            yield Input(
                value=str(self.default_max_chars),
                type="integer",
                id="max-chars",
            )
            yield Static("输出目录")
            yield Input(value=str(Path.cwd() / "output"), id="output")
            yield Static("Tab 切换 · Enter 确认 · Esc 取消", id="hint")
            yield Static("", id="status")
            yield Static("", id="confirmation")
            yield Button("检查设置", id="start", variant="primary")
            yield Button("取消", id="cancel")

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
