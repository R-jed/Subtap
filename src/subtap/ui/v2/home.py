"""Signal Desk home screen."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

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

#brand-wide, #brand-compact {
    height: auto;
    color: $primary;
    text-style: bold;
}

#brand-wide {
    display: none;
}

HomeScreen.-wide #brand-wide {
    display: block;
}

HomeScreen.-wide #brand-compact {
    display: none;
}

#product-copy {
    height: auto;
    margin-bottom: 1;
    color: $text-muted;
}

#workspace-label {
    height: auto;
    color: $text-muted;
    text-style: bold;
}

#home-actions {
    height: auto;
    max-height: 7;
}
"""


class HomeScreen(Screen[None]):
    """Choose the next Subtap task."""

    def compose(self) -> ComposeResult:
        with Vertical(id="home-shell"):
            yield Static(
                "█████ ██  ██ █████  ██████  █████  ██████\n"
                "██    ██  ██ ██  ██   ██   ██   ██ ██  ██\n"
                "█████  ████  █████    ██   ███████ █████",
                id="brand-wide",
            )
            yield Static("SUBTAP", id="brand-compact")
            yield Static(
                "本地优先的字幕工作台\n"
                "专为 Apple 芯片设计，音视频与模型推理均留在本机",
                id="product-copy",
            )
            yield Static("工作台", id="workspace-label")
            yield OptionList(
                *(
                    Option(
                        f"{'> ' if index == 0 else '  '}{label}",
                        id=action,
                    )
                    for index, (label, action) in enumerate(HOME_OPTIONS)
                ),
                id="home-actions",
            )
        yield Footer(compact=True, show_command_palette=False)

    @on(OptionList.OptionSelected)
    def option_selected(self, event: OptionList.OptionSelected) -> None:
        action = event.option.id
        if action not in HOME_ACTIONS:
            raise ValueError(f"Unknown Home action: {action!r}")
        if action == "run":
            from .new_transcription import NewTranscriptionScreen

            self.app.push_screen(NewTranscriptionScreen(), self._finish_transcription)
            return
        self.app.exit(action)

    def _finish_transcription(self, command: list[str] | None) -> None:
        if command is not None:
            self.app.exit(command)

    @on(OptionList.OptionHighlighted)
    def option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        menu = event.option_list
        for index, (label, _) in enumerate(HOME_OPTIONS):
            prefix = "> " if index == event.option_index else "  "
            menu.replace_option_prompt_at_index(index, f"{prefix}{label}")
