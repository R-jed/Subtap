"""Independent Textual composition root for Subtap TUI v2."""

from textual.app import App
from textual.binding import Binding
from textual.screen import Screen

from .home import HOME_CSS, HomeScreen
from .theme import HORIZONTAL_BREAKPOINTS, SIGNAL_DESK_CSS, SIGNAL_DESK_THEME


class SubtapV2App(App[str | list[str] | None]):
    """Signal Desk application shell."""

    TITLE = "subtap"
    ENABLE_COMMAND_PALETTE = False
    HORIZONTAL_BREAKPOINTS = HORIZONTAL_BREAKPOINTS
    CSS = SIGNAL_DESK_CSS + HOME_CSS
    BINDINGS = [
        Binding("escape", "back", "返回", priority=True),
        Binding("q", "quit", "退出", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.register_theme(SIGNAL_DESK_THEME)
        self.theme = SIGNAL_DESK_THEME.name

    def get_default_screen(self) -> Screen:
        return HomeScreen()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "back" and len(self.screen_stack) == 1:
            return False
        return True
