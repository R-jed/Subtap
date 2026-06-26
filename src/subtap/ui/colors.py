"""TUI color scheme for Subtap."""

from rich.style import Style

# Stage titles
STAGE_TITLE = Style(color="blue", bold=True)

# Progress bar states
PROGRESS_BAR = Style(color="green")
PROGRESS_ACTIVE = Style(color="yellow")

# Status indicators
SUCCESS = Style(color="green", bold=True)
ERROR = Style(color="red", bold=True)

# Information display
FILE_PATH = Style(color="cyan")
TIMING = Style(dim=True)
HEADER = Style(color="white", bold=True)

# Summary panel
SUMMARY_BORDER = Style(color="blue")
SUMMARY_TITLE = Style(color="white", bold=True)
