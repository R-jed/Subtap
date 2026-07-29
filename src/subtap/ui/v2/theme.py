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

.desk-shell {
    width: 100%;
    max-width: 104;
    height: 1fr;
    padding: 2 3 1 3;
}

.desk-title {
    height: auto;
    color: $primary;
    text-style: bold;
}

.page-header {
    height: auto;
}

.desk-copy {
    height: auto;
    color: $text-muted;
    margin-bottom: 2;
}

.desk-label {
    height: auto;
    color: $text-muted;
    text-style: bold;
    margin-top: 1;
}

.desk-note, #batch-status, #preference-status {
    height: auto;
    color: $text-muted;
    padding: 1 0;
}

.desk-row, .desk-actions {
    height: 3;
}

.desk-row .desk-value {
    width: 1fr;
    height: 3;
    padding: 1;
    background: $surface;
}

.desk-row Button {
    width: 18;
    margin-left: 1;
}

.desk-actions {
    margin-top: 2;
}

.desk-actions Button {
    width: 1fr;
}

.desk-actions Button:first-of-type {
    margin-right: 1;
}

.resource-card, .check-card {
    height: auto;
    padding: 1 0;
    margin-bottom: 1;
}

.check-card.success {
    color: $success;
}

.check-card.blocked {
    color: $error;
}

.check-card.warning {
    color: $warning;
}

.check-card.ok {
    color: $success;
}

.resource-card.success {
    color: $success;
}

.resource-card.blocked {
    color: $warning;
}

Screen.-compact .desk-row,
Screen.-compact .desk-actions {
    height: auto;
    layout: vertical;
}

Screen.-compact .desk-row .desk-value,
Screen.-compact .desk-row Button,
Screen.-compact .desk-actions Button {
    width: 100%;
    margin: 0 0 1 0;
}
"""
