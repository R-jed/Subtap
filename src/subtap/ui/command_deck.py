"""Command Deck entry UI."""

from __future__ import annotations

from dataclasses import dataclass
import sys

from rich.text import Text

from subtap import __version__
from subtap.ui.theme import (
    CALM_WORKBENCH_BREAKPOINTS,
    CALM_WORKBENCH_CSS,
    RICH_ACCENT,
    RICH_LINK,
    RICH_LOGO,
    RICH_MUTED,
    RICH_TEXT,
)

SOLID_SUBTAP_ASCII = """
█████ ██  ██ ████  █████  ███  ████
██    ██  ██ ██ ██   ██  ██ ██ ██ ██
█████ ██  ██ ████    ██  █████ ████
   ██ ██  ██ ██ ██   ██  ██ ██ ██
█████  ████  ████    ██  ██ ██ ██
"""


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

STYLE_LOGO = RICH_LOGO
STYLE_TEXT = RICH_TEXT
STYLE_MUTED = RICH_MUTED
STYLE_ACCENT = RICH_ACCENT
STYLE_LINK = RICH_LINK

FOOTER_KEYS = "↑↓  移动   Enter  选择   Q  退出"


def _build_header_renderable() -> Text:
    """Render the product identity with its description below the logo."""
    text = Text(SOLID_SUBTAP_ASCII.strip("\n"), style=STYLE_LOGO)
    text.append("\nSUBTAP", style=f"bold {STYLE_TEXT}")
    text.append("\n本地离线字幕生成", style=STYLE_MUTED)
    text.append(f"\n{PROJECT_URL}  ·  v{__version__}", style=STYLE_LINK)
    return text


def _build_compact_header_renderable() -> Text:
    return Text.assemble(
        ("SUBTAP", f"bold {STYLE_TEXT}"),
        ("\n本地离线字幕生成", STYLE_MUTED),
        (f"\n{PROJECT_URL}  ·  v{__version__}", STYLE_LINK),
    )


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
    lines.append(SOLID_SUBTAP_ASCII.strip("\n"))
    lines.append("SUBTAP")
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
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import Footer, OptionList, Static
    from textual.widgets.option_list import Option

    class CommandDeckApp(App[str | list[str] | None]):
        """Keyboard-first local subtitle command deck."""

        TITLE = "subtap"
        HORIZONTAL_BREAKPOINTS = CALM_WORKBENCH_BREAKPOINTS

        CSS = CALM_WORKBENCH_CSS + """
        Screen {
            align: center top;
        }

        #home-shell {
            width: 100%;
            max-width: 104;
            height: 1fr;
            padding: 1 2 0 2;
        }
        #brand-wide, #brand-compact { height: auto; margin-bottom: 1; }
        #brand-wide { display: none; }
        Screen.-wide #brand-wide { display: block; }
        Screen.-wide #brand-compact { display: none; }
        #menu {
            height: auto;
            max-height: 8;
            padding: 0;
            background: $background;
            border: none;
        }
        #menu > .option-list--option-highlighted {
            background: $background;
            color: $foreground;
            text-style: none;
        }
        #menu:focus {
            border: none;
            background: $background;
            background-tint: transparent;
        }
        #menu:focus > .option-list--option-highlighted {
            background: $background;
            color: $foreground;
            text-style: none;
        }
        """

        BINDINGS = [
            Binding("up", "cursor_up", "上移", show=False),
            Binding("down", "cursor_down", "下移", show=False),
            Binding("j", "cursor_down", "下移", show=False),
            Binding("enter", "select", "选择"),
            Binding("k", "cursor_up", "上移", show=False),
            *[
                Binding(
                    str(index + 1),
                    f"select_index({index})",
                    option.label,
                    show=False,
                )
                for index, option in enumerate(OPTIONS)
            ],
            Binding("o", "open_output", "输出"),
            Binding("d", "doctor", "诊断"),
            Binding("v", "version", "版本", show=False),
            Binding("q", "quit", "退出"),
        ]

        def __init__(self) -> None:
            super().__init__()
            self.selected_index: int = 0

        @property
        def current_option(self) -> CommandDeckOption:
            return OPTIONS[self.selected_index]

        def compose(self) -> ComposeResult:
            with Vertical(id="home-shell"):
                yield Static(_build_header_renderable(), id="brand-wide")
                yield Static(_build_compact_header_renderable(), id="brand-compact")
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
            self._select_action(self.current_option.action)

        @on(OptionList.OptionSelected)
        def option_selected(self, event: OptionList.OptionSelected) -> None:
            if event.option.id is not None:
                self._select_action(event.option.id)

        @on(OptionList.OptionHighlighted)
        def option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
            self.selected_index = event.option_index
            self._refresh_option_prompts()

        def action_select_index(self, index: int) -> None:
            if 0 <= index < len(OPTIONS):
                self.selected_index = index
                self._select_action(self.current_option.action)

        def _select_action(self, action: str) -> None:
            if action == "run":
                from subtap.ui.textual_run_setup import RunSetupScreen

                self.push_screen(RunSetupScreen(), self._finish_command)
                return
            from subtap.ui.textual_command_pages import (
                CommandOutputPage,
                GlossaryPage,
                LaunchCommandPage,
                batch_page,
                observe_page,
            )

            if action == "batch":
                self.push_screen(batch_page(), self._finish_command)
            elif action == "observe":
                self.push_screen(observe_page())
            elif action == "models":
                self.push_screen(
                    CommandOutputPage(
                        "模型",
                        "查看当前任务所需模型的本地状态。",
                        [sys.executable, "-m", "subtap.cli", "models", "status"],
                    )
                )
            elif action == "glossary":
                self.push_screen(GlossaryPage())
            elif action == "setup":
                self.push_screen(
                    LaunchCommandPage(
                        "设置",
                        "打开默认模型与服务配置向导；完成后返回终端。",
                        [sys.executable, "-m", "subtap.cli", "setup"],
                    ),
                    self._finish_command,
                )
            elif action == "doctor":
                self.push_screen(
                    CommandOutputPage(
                        "环境检查",
                        "检查安装、模型与运行环境。",
                        [sys.executable, "-m", "subtap.cli", "doctor"],
                    )
                )
            else:
                self.exit(action)

        def _finish_command(self, command: list[str] | None) -> None:
            if command is not None:
                self.exit(command)

        def action_open_output(self) -> None:
            self.exit("output")

        def action_doctor(self) -> None:
            self._select_action("doctor")

        def action_version(self) -> None:
            self.exit("version")

        def check_action(
            self, action: str, parameters: tuple[object, ...]
        ) -> bool | None:
            if len(self.screen_stack) > 1 and action in {
                "cursor_up",
                "cursor_down",
                "select",
                "select_index",
                "open_output",
                "doctor",
                "version",
            }:
                return False
            return True

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
