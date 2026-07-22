"""Command Deck entry UI."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from subtap.ui.observer import SUBTAP_ASCII


@dataclass(frozen=True)
class CommandDeckOption:
    label: str
    description: str
    action: str


OPTIONS = [
    CommandDeckOption("Run", "选择参数并从音频生成字幕", "run"),
    CommandDeckOption("Observe", "观察已有 run.log.jsonl", "observe"),
    CommandDeckOption("Batch", "批量处理媒体文件夹", "batch"),
    CommandDeckOption("Doctor", "检查模型和本地运行环境", "doctor"),
    CommandDeckOption("Setup", "检查环境和管理模型", "setup"),
]

PROJECT_URL = "https://github.com/R-jed/Subtap"

STYLE_LOGO = "#8a8a8a"
STYLE_TEXT = "#f2f2f2"
STYLE_MUTED = "#8b8b92"
STYLE_ACCENT = "#56d4dd"
STYLE_LINK = "#78a9ff"

FOOTER_KEYS = "↑↓  |  Enter 选择  |  O 输出  |  D 诊断  |  V 版本  |  Q 退出"


def build_root_command_deck(selected_index: int = 0) -> str:
    """Render the root Command Deck menu."""
    lines: list[str] = []
    lines.append("       Subtap Command Deck  ")
    lines.append(SUBTAP_ASCII)
    lines.append("                           本地优先字幕生成流水线。")
    lines.append("")
    for index, option in enumerate(OPTIONS):
        marker = ">" if index == selected_index else " "
        lines.append(f"{marker} {option.label}. {option.description}")
    lines.extend(["", FOOTER_KEYS])
    return "\n".join(lines)


def build_root_command_deck_renderable(selected_index: int = 0) -> Text:
    """Render the root Command Deck with reference-image colors."""
    text = Text()
    logo_lines = SUBTAP_ASCII.splitlines()
    for index, line in enumerate(logo_lines):
        if index > 0:
            text.append("\n")
        text.append(line, style=STYLE_LOGO)
    text.append("\n       Subtap Command Deck  ", style=STYLE_TEXT)
    text.append("\n")
    text.append(
        "                           本地优先字幕生成流水线。\n\n", style=STYLE_MUTED
    )
    text.append(PROJECT_URL, style=STYLE_LINK)
    for index, option in enumerate(OPTIONS):
        marker = ">" if index == selected_index else " "
        text.append(f"\n{marker} ", style=STYLE_ACCENT)
        text.append(f"{option.label}. ", style=STYLE_TEXT)
        text.append(option.description, style=STYLE_MUTED)
    text.append(f"\n\n{FOOTER_KEYS}", style=STYLE_MUTED)
    return text


try:
    from textual.app import App, ComposeResult
    from textual import on
    from textual.widgets import Footer, OptionList, Static
    from textual.widgets.option_list import Option

    class CommandDeckApp(App[str]):
        """Keyboard-first local subtitle command deck."""

        CSS = """
        Screen {
            background: #0b0d10;
            color: #f2f2f2;
        }

        #brand { color: #8a8a8a; height: auto; margin: 1 3 0 3; }
        #tagline { color: #8b8b92; height: auto; margin: 0 3 1 3; }
        #project { color: #78a9ff; height: auto; margin: 0 3 1 3; }
        #menu { height: 1fr; margin: 0 3; background: #0b0d10; border: none; }
        #menu > .option-list--option-highlighted {
            background: #123238;
            color: #56d4dd;
            text-style: bold;
        }
        Footer { background: #0b0d10; color: #8b8b92; }
        """

        BINDINGS = [
            ("up", "cursor_up", "上移"),
            ("down", "cursor_down", "下移"),
            ("j", "cursor_down", "下移"),
            ("enter", "select", "选择"),
            ("k", "cursor_up", "上移"),
            ("1", "select_index(0)", "Run"),
            ("2", "select_index(1)", "Observe"),
            ("3", "select_index(2)", "Batch"),
            ("4", "select_index(3)", "Doctor"),
            ("5", "select_index(4)", "Setup"),
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
            yield Static(SUBTAP_ASCII, id="brand")
            yield Static("Subtap · 本地离线字幕生成", id="tagline")
            yield Static(PROJECT_URL, id="project")
            yield OptionList(
                *[
                    Option(
                        Text.assemble(
                            (f"{index + 1}. {option.label}", STYLE_TEXT),
                            (f"  {option.description}", STYLE_MUTED),
                        ),
                        id=option.action,
                    )
                    for index, option in enumerate(OPTIONS)
                ],
                id="menu",
            )
            yield Footer()

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

except ModuleNotFoundError:

    class CommandDeckApp:  # type: ignore[no-redef]
        """Placeholder used when Textual is not installed."""

        def __init__(self) -> None:
            raise RuntimeError("Textual 未安装，无法启动交互式 Command Deck")

        def run(self) -> str | None:
            raise RuntimeError("Textual 未安装，无法启动交互式 Command Deck")
