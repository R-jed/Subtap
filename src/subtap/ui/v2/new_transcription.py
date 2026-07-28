"""Signal Desk page for configuring one transcription."""

from __future__ import annotations

import logging
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, Select, Static

from subtap.core.models import asr_mode_for_model
from subtap.schemas.config import load_config
from subtap.ui.native_picker import choose_file, choose_folder
from subtap.ui.views.wizard import WizardView

from .theme import HORIZONTAL_BREAKPOINTS

logger = logging.getLogger(__name__)


class ReviewTranscriptionScreen(ModalScreen[bool]):
    """Confirm the expensive task without discarding the configured form."""

    BINDINGS = [
        Binding("escape", "cancel", "返回", priority=True),
    ]
    CSS = """
    ReviewTranscriptionScreen {
        align: center middle;
        background: $background 70%;
    }
    #review-dialog {
        width: 64;
        height: auto;
        max-height: 90%;
        padding: 2 3;
        background: $surface;
    }
    #review-title {
        height: auto;
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    #review-summary {
        height: auto;
        color: $text-muted;
        margin-bottom: 1;
    }
    #review-actions {
        height: 3;
    }
    #review-actions Button {
        width: 1fr;
    }
    #review-cancel {
        margin-right: 1;
    }
    """

    def __init__(self, summary: str) -> None:
        super().__init__()
        self.summary = summary

    def compose(self) -> ComposeResult:
        with Vertical(id="review-dialog"):
            yield Static("复核转录设置", id="review-title")
            yield Static(self.summary, id="review-summary")
            with Horizontal(id="review-actions"):
                yield Button("返回修改", id="review-cancel")
                yield Button("开始转录", id="review-confirm", variant="primary")

    @on(Button.Pressed, "#review-cancel")
    def cancel(self) -> None:
        self.action_cancel()

    @on(Button.Pressed, "#review-confirm")
    def confirm(self) -> None:
        self.action_confirm()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)


class NewTranscriptionScreen(Screen[list[str] | None]):
    """Collect every setting needed by the existing ``subtap run`` command."""

    HORIZONTAL_BREAKPOINTS = HORIZONTAL_BREAKPOINTS
    CSS = """
    NewTranscriptionScreen {
        align: center top;
    }

    #new-shell {
        width: 100%;
        max-width: 104;
        height: 1fr;
        padding: 1 2 0 2;
    }

    #screen-title {
        height: auto;
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }

    .field-label {
        height: auto;
        color: $text-muted;
    }

    #media-row, .resource-row, #action-row {
        height: 3;
        margin-bottom: 1;
    }

    #media-path {
        width: 1fr;
        padding: 1;
        background: $surface;
    }

    .resource-row Select, .resource-row Input {
        width: 1fr;
    }

    #choose-media, .resource-row Button {
        width: 18;
        margin-left: 1;
    }

    #workbench {
        grid-size: 2 1;
        grid-columns: 2fr 1fr;
        grid-gutter: 1 2;
        height: auto;
    }

    #settings, #summary-pane {
        height: auto;
    }

    #quality, #max-chars {
        margin-bottom: 1;
    }

    #summary-pane {
        padding: 1 2;
        background: $surface;
    }

    #summary-title {
        height: auto;
        text-style: bold;
        margin-bottom: 1;
    }

    #summary {
        height: auto;
        color: $text-muted;
    }

    #status {
        min-height: 1;
        height: auto;
        color: $error;
    }

    #action-row {
        margin-top: 1;
    }

    #action-row Button {
        width: 1fr;
    }

    #back {
        margin-right: 1;
    }

    NewTranscriptionScreen.-compact #workbench {
        grid-size: 1 2;
        grid-columns: 1fr;
    }

    NewTranscriptionScreen.-compact #summary-pane {
        margin-top: 1;
    }
    """

    def __init__(self, input_path: Path | None = None) -> None:
        super().__init__()
        self.input_path = input_path
        config = load_config(Path.home() / ".subtap" / "config.yaml")
        self.default_mode = asr_mode_for_model(config.asr.model)
        self.default_max_chars = config.output.max_chars
        self._glossary_options = [
            ("默认热词表 · default.txt", ""),
            *[
                (
                    f"{'自动学习' if path.name == 'learned.txt' else '本地热词表'}"
                    f" · {path.name}",
                    str(path),
                )
                for path in WizardView.list_glossaries()
                if path.name != "default.txt"
            ],
        ]
        self._manuscript_options = [
            ("不使用参考文稿", ""),
            *[
                (f"本地文稿 · {path.name}", str(path))
                for path in WizardView.list_manuscripts()
            ],
        ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="new-shell"):
            yield Static("新建字幕", id="screen-title")
            yield Static("媒体文件", classes="field-label")
            with Horizontal(id="media-row"):
                yield Static(
                    str(self.input_path) if self.input_path else "尚未选择媒体文件",
                    id="media-path",
                )
                yield Button("选择…", id="choose-media")
            with Grid(id="workbench"):
                with Vertical(id="settings"):
                    yield Static("任务设置", id="settings-title")
                    yield Static("转录质量", classes="field-label")
                    yield Select(
                        [
                            ("快速 · 0.6B", "fast"),
                            ("高质量 · 1.7B", "quality"),
                        ],
                        value=self.default_mode,
                        id="quality",
                    )
                    yield Static("热词表", classes="field-label")
                    with Horizontal(classes="resource-row"):
                        yield Select(
                            self._glossary_options,
                            value="",
                            id="glossary",
                        )
                        yield Button("选择…", id="choose-glossary")
                    yield Static("参考文稿", classes="field-label")
                    with Horizontal(classes="resource-row"):
                        yield Select(
                            self._manuscript_options,
                            value="",
                            id="manuscript",
                        )
                        yield Button("选择…", id="choose-manuscript")
                    yield Static(
                        "字幕目标最大字数（建议 25；范围 10–60）",
                        classes="field-label",
                    )
                    yield Input(
                        value=str(self.default_max_chars),
                        type="integer",
                        id="max-chars",
                    )
                    yield Static("输出目录", classes="field-label")
                    with Horizontal(classes="resource-row"):
                        yield Input(value=str(Path.cwd() / "output"), id="output")
                        yield Button("选择…", id="choose-output")
                with Vertical(id="summary-pane"):
                    yield Static("设置摘要", id="summary-title")
                    yield Static("", id="summary")
            yield Static("", id="status")
            with Horizontal(id="action-row"):
                yield Button("返回", id="back")
                yield Button(
                    "开始转录",
                    id="start",
                    variant="primary",
                )
        yield Footer(compact=True, show_command_palette=False)

    def on_mount(self) -> None:
        self._update_summary()

    def action_back(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.action_back()

    def _pick(self, chooser, prompt: str) -> Path | None:
        try:
            return chooser(prompt)
        except RuntimeError as error:
            logger.exception("无法打开系统选择器：%s", prompt)
            self.query_one("#status", Static).update(f"无法打开系统选择器：{error}")
            return None

    def _set_select_path(
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

    @on(Button.Pressed, "#choose-media")
    def choose_media(self) -> None:
        path = self._pick(choose_file, "选择音频或视频文件")
        if path is not None:
            self.input_path = path
            self.query_one("#media-path", Static).update(str(path))
            self._update_summary()

    @on(Button.Pressed, "#choose-glossary")
    def choose_glossary(self) -> None:
        path = self._pick(choose_file, "选择本地热词表")
        if path is not None:
            self._set_select_path(
                "#glossary", self._glossary_options, path, "本地热词表"
            )

    @on(Button.Pressed, "#choose-manuscript")
    def choose_manuscript(self) -> None:
        path = self._pick(choose_file, "选择参考文稿")
        if path is not None:
            self._set_select_path(
                "#manuscript", self._manuscript_options, path, "本地文稿"
            )

    @on(Button.Pressed, "#choose-output")
    def choose_output(self) -> None:
        path = self._pick(choose_folder, "选择字幕输出目录")
        if path is not None:
            self.query_one("#output", Input).value = str(path)

    @on(Select.Changed)
    @on(Input.Changed)
    def settings_changed(self) -> None:
        self._update_summary()

    def _update_summary(self) -> None:
        quality = self.query_one("#quality", Select).value
        glossary = self.query_one("#glossary", Select).value
        manuscript = self.query_one("#manuscript", Select).value
        output = self.query_one("#output", Input).value.strip()
        summary = [
            self.input_path.name if self.input_path else "尚未选择媒体文件",
            "高质量" if quality == "quality" else "快速",
            (
                Path(glossary).name
                if isinstance(glossary, str) and glossary
                else "默认热词表"
            ),
            (
                Path(manuscript).name
                if isinstance(manuscript, str) and manuscript
                else "不使用参考文稿"
            ),
            output or "尚未选择输出目录",
        ]
        self.query_one("#summary", Static).update("\n".join(summary))

    @on(Button.Pressed, "#start")
    def start(self) -> None:
        status = self.query_one("#status", Static)
        if self.input_path is None:
            status.update("请选择音频或视频文件")
            return
        output = self.query_one("#output", Input).value.strip()
        if not output:
            status.update("请选择输出目录")
            return
        try:
            max_chars = int(self.query_one("#max-chars", Input).value)
        except ValueError:
            status.update("字幕最大字数必须是 10 到 60 的整数")
            return
        if not 10 <= max_chars <= 60:
            status.update("字幕最大字数必须在 10 到 60 之间")
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
            status.update(str(error))
            return
        if command[-1:] != ["--tui"]:
            raise RuntimeError("WizardView 未生成预期的 TUI 观察参数")
        command[-1] = "--tui-v2"
        status.update("")
        summary = (
            f"媒体文件\n{self.input_path}\n\n"
            f"输出目录\n{Path(output).expanduser()}\n\n"
            f"转录质量\n{'高质量 · 1.7B' if quality == 'quality' else '快速 · 0.6B'}\n\n"
            f"字幕目标\n最多 {max_chars} 字"
        )
        self.app.push_screen(
            ReviewTranscriptionScreen(summary),
            lambda confirmed: self._finish_review(confirmed, command),
        )

    def _finish_review(self, confirmed: bool | None, command: list[str]) -> None:
        if confirmed:
            self.dismiss(command)
