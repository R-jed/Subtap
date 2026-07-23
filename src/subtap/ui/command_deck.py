"""Command Deck entry UI."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from subtap import __version__
from subtap.ui.observer import SUBTAP_ASCII


@dataclass(frozen=True)
class CommandDeckOption:
    label: str
    description: str
    action: str


OPTIONS = [
    CommandDeckOption("Transcribe", "单个音频或视频生成字幕", "run"),
    CommandDeckOption("Batch", "批量转录多个媒体文件", "batch"),
    CommandDeckOption("Observe", "查看正在运行或历史任务", "observe"),
    CommandDeckOption("Models", "查看本地模型状态", "models"),
    CommandDeckOption("Glossary", "维护默认热词和查看学习结果", "glossary"),
    CommandDeckOption("Setup", "更改默认模型和服务配置", "setup"),
    CommandDeckOption("Doctor", "检查安装和运行环境", "doctor"),
]

PROJECT_URL = "https://github.com/R-jed/Subtap"

STYLE_LOGO = "#8a8a8a"
STYLE_TEXT = "#f2f2f2"
STYLE_MUTED = "#8b8b92"
STYLE_ACCENT = "#56d4dd"
STYLE_LINK = "#78a9ff"

FOOTER_KEYS = "↑↓  移动   Enter  选择   Q  退出"


def _build_header_renderable() -> Text:
    """Render a compact product header without network work."""
    side_lines = [
        ("subtap", STYLE_TEXT),
        (PROJECT_URL, STYLE_LINK),
        ("本地离线字幕生成", STYLE_MUTED),
        (f"v{__version__}", STYLE_MUTED),
    ]
    text = Text()
    logo_lines = SUBTAP_ASCII.strip("\n").splitlines()
    logo_width = max(len(line) for line in logo_lines)
    for index in range(max(len(logo_lines), len(side_lines))):
        if index:
            text.append("\n")
        line = logo_lines[index] if index < len(logo_lines) else ""
        text.append(line.ljust(logo_width), style=STYLE_LOGO)
        if index < len(side_lines):
            value, style = side_lines[index]
            text.append("   ")
            text.append(value, style=style)
    return text


def _build_option_prompt(index: int, selected: bool) -> Text:
    """Build one menu row with a compact selection marker."""
    option = OPTIONS[index]
    marker = "➤" if selected else " "
    label_style = f"bold {STYLE_ACCENT}" if selected else STYLE_TEXT
    return Text.assemble(
        (f"{marker} {index + 1}. ", STYLE_ACCENT if selected else STYLE_MUTED),
        (option.label, label_style),
        (f"   {option.description}", STYLE_MUTED),
    )


def build_root_command_deck(selected_index: int = 0) -> str:
    """Render the root Command Deck menu."""
    lines: list[str] = []
    lines.append(SUBTAP_ASCII.strip("\n"))
    lines.append("本地离线字幕生成")
    lines.append(PROJECT_URL)
    lines.append("")
    for index, option in enumerate(OPTIONS):
        marker = "➤" if index == selected_index else " "
        lines.append(f"{marker} {index + 1}. {option.label}   {option.description}")
    lines.extend(["", FOOTER_KEYS])
    return "\n".join(lines)


def build_root_command_deck_renderable(selected_index: int = 0) -> Text:
    """Render the root Command Deck with reference-image colors."""
    text = _build_header_renderable()
    text.append("\n\n")
    for index in range(len(OPTIONS)):
        if index:
            text.append("\n")
        text.append_text(_build_option_prompt(index, index == selected_index))
    text.append(f"\n\n{FOOTER_KEYS}", style=STYLE_MUTED)
    return text


try:
    from textual.app import App, ComposeResult
    from textual import on
    from textual.widgets import OptionList, Static
    from textual.widgets.option_list import Option

    class CommandDeckApp(App[str]):
        """Keyboard-first local subtitle command deck."""

        TITLE = "subtap"

        CSS = """
        Screen {
            background: #0b0d10;
            color: #f2f2f2;
        }

        #brand { height: auto; margin: 1 2 1 2; }
        #menu {
            height: auto;
            max-height: 8;
            margin: 0 2;
            padding: 0;
            background: #0b0d10;
            border: none;
        }
        #menu > .option-list--option-highlighted {
            background: #0b0d10;
            color: #f2f2f2;
            text-style: none;
        }
        #menu:focus {
            border: none;
            background: #0b0d10;
            background-tint: transparent;
        }
        #menu:focus > .option-list--option-highlighted {
            background: #0b0d10;
            color: #f2f2f2;
            text-style: none;
        }
        #keys { color: #66666d; height: auto; margin: 1 2 0 2; }
        """

        BINDINGS = [
            ("up", "cursor_up", "上移"),
            ("down", "cursor_down", "下移"),
            ("j", "cursor_down", "下移"),
            ("enter", "select", "选择"),
            ("k", "cursor_up", "上移"),
            *[
                (str(index + 1), f"select_index({index})", option.label)
                for index, option in enumerate(OPTIONS)
            ],
            ("o", "open_output", "输出"),
            ("d", "doctor", "诊断"),
            ("v", "version", "版本"),
            ("q", "quit", "退出"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.selected_index: int = 0

        @property
        def current_option(self) -> CommandDeckOption:
            return OPTIONS[self.selected_index]

        def compose(self) -> ComposeResult:
            yield Static(_build_header_renderable(), id="brand")
            yield OptionList(
                *[
                    Option(
                        _build_option_prompt(index, index == self.selected_index),
                        id=option.action,
                    )
                    for index, option in enumerate(OPTIONS)
                ],
                id="menu",
            )
            yield Static(FOOTER_KEYS, id="keys")

        def on_mount(self) -> None:
            from subtap.ui.views.home import HomeView

            if HomeView().is_first_run():
                from subtap.ui.textual_first_run import FirstRunScreen

                self.push_screen(FirstRunScreen())

        def action_cursor_down(self) -> None:
            self.selected_index = (self.selected_index + 1) % len(OPTIONS)
            self._refresh_deck()

        def action_cursor_up(self) -> None:
            self.selected_index = (self.selected_index - 1) % len(OPTIONS)
            self._refresh_deck()

        def action_select(self) -> None:
            self.exit(self.current_option.action)

        @on(OptionList.OptionSelected)
        def option_selected(self, event: OptionList.OptionSelected) -> None:
            if event.option.id is not None:
                self.exit(event.option.id)

        @on(OptionList.OptionHighlighted)
        def option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
            self.selected_index = event.option_index
            self._refresh_option_prompts()

        def action_select_index(self, index: int) -> None:
            if 0 <= index < len(OPTIONS):
                self.selected_index = index
                self.exit(self.current_option.action)

        def action_open_output(self) -> None:
            self.exit("output")

        def action_doctor(self) -> None:
            self.exit("doctor")

        def action_version(self) -> None:
            self.exit("version")

        def _refresh_deck(self) -> None:
            self.query_one("#menu", OptionList).highlighted = self.selected_index

        def _refresh_option_prompts(self) -> None:
            menu = self.query_one("#menu", OptionList)
            for index in range(len(OPTIONS)):
                menu.replace_option_prompt_at_index(
                    index,
                    _build_option_prompt(index, index == self.selected_index),
                )

except ModuleNotFoundError:

    class CommandDeckApp:  # type: ignore[no-redef]
        """Placeholder used when Textual is not installed."""

        def __init__(self) -> None:
            raise RuntimeError("Textual 未安装，无法启动交互式 Command Deck")

        def run(self) -> str | None:
            raise RuntimeError("Textual 未安装，无法启动交互式 Command Deck")
