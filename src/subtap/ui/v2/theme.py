"""Signal Desk theme shared by every TUI v2 screen."""

from textual.theme import Theme

HORIZONTAL_BREAKPOINTS = [
    (0, "-compact"),
    (80, "-regular"),
    (104, "-wide"),
]

SIGNAL_DESK_THEME = Theme(
    name="signal-desk",
    primary="#63C5CF",
    success="#72C48B",
    warning="#D4AA60",
    error="#D76D74",
    foreground="#E6EBEF",
    background="#0B0E11",
    surface="#11171C",
    panel="#182027",
    dark=True,
    variables={"text-muted": "#89949E", "elevated": "#182027"},
)

SIGNAL_DESK_CSS = """
Screen {
    background: $background;
    color: $foreground;
}

Footer {
    background: $surface;
    color: $text-muted;
}

OptionList {
    background: $background;
    border: none;
}

OptionList:focus {
    border: none;
}

OptionList > .option-list--option-highlighted {
    background: $surface;
    color: $primary;
    text-style: bold;
}
"""
