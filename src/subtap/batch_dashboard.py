"""Batch transcription TUI dashboard using Textual."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ProgressBar
from textual.containers import Container, Horizontal, Vertical

from subtap.ui.dashboard import STAGE_CN


@dataclass
class BatchItem:
    """State for a single batch item."""

    input_path: str
    output_dir: str = ""
    status: str = "pending"  # pending, running, succeeded, failed, interrupted
    progress: int = 0
    stage: str = ""
    duration: float = 0.0
    error: str = ""


@dataclass
class BatchState:
    """Overall batch state."""

    total: int = 0
    current_index: int = 0
    current_file: Optional[str] = None
    items: list[BatchItem] = field(default_factory=list)
    mode: str = "fast"
    start_time: float = 0.0


class TotalProgressPanel(Static):
    """Total progress display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._completed = 0
        self._total = 0

    def update_progress(self, completed: int, total: int) -> None:
        self._completed = completed
        self._total = total
        self.update(f"总进度：{completed}/{total} 文件")


class CurrentFilePanel(Static):
    """Current file display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._filename = ""

    def update_file(self, filename: str) -> None:
        self._filename = filename
        self.update(f"▸ 当前：{filename}")


class StageProgressPanel(Static):
    """Stage progress display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stage = ""
        self._progress = 0

    def update_stage(self, stage: str, progress: int) -> None:
        self._stage = STAGE_CN.get(stage, stage)
        self._progress = progress
        bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
        self.update(f"[{self._stage}]\n进度：{bar} {progress}%")


class FileListPanel(Static):
    """File list display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items: list[BatchItem] = []

    def update_items(self, items: list[BatchItem]) -> None:
        self._items = items
        lines = []
        for item in items:
            if item.status == "succeeded":
                icon = "[green]✓[/green]"
                detail = f"{item.duration:.1f}s"
            elif item.status == "failed":
                icon = "[red]✗[/red]"
                detail = "failed"
            elif item.status == "running":
                icon = "[yellow]⏳[/yellow]"
                detail = f"{item.stage} {item.progress}%"
            elif item.status == "interrupted":
                icon = "[red]⊘[/red]"
                detail = "interrupted"
            else:
                icon = "[dim]○[/dim]"
                detail = "pending"

            name = item.input_path.split("/")[-1][:40]
            lines.append(f"{icon} {name:40} {detail}")

        self.update("\n".join(lines))


class BatchDashboard(App):
    """Textual app for batch transcription monitoring."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 1;
        grid-rows: 1fr 1fr 2fr 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.state = BatchState()
        self.total_panel = TotalProgressPanel()
        self.file_panel = CurrentFilePanel()
        self.stage_panel = StageProgressPanel()
        self.file_list = FileListPanel()

    def compose(self) -> ComposeResult:
        yield Header()
        yield self.total_panel
        yield self.file_panel
        yield self.stage_panel
        yield self.file_list
        yield Footer()

    def update_state(self, state: BatchState) -> None:
        """Update dashboard state."""
        self.state = state

        # Count completed
        completed = sum(
            1
            for item in state.items
            if item.status in ("succeeded", "failed", "interrupted")
        )
        self.total_panel.update_progress(completed, state.total)

        # Current file
        if state.current_file:
            self.file_panel.update_file(state.current_file)

        # Current stage
        if state.items and state.current_index < len(state.items):
            current = state.items[state.current_index]
            self.stage_panel.update_stage(current.stage, current.progress)

        # File list
        self.file_list.update_items(state.items)
