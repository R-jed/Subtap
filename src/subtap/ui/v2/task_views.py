"""Task state views for TUI v2."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import Screen
from textual.widgets import ProgressBar, RichLog, Static
from textual.widget import Widget

from subtap.ui.observer import TaskPresentation

from .components import TaskDetails, TaskPipeline, TaskStatus
from .theme import HORIZONTAL_BREAKPOINTS as SIGNAL_DESK_BREAKPOINTS


def _status_kind(status: str) -> str:
    normalized = status.casefold()
    if any(token in normalized for token in ("中断", "取消", "interrupt", "cancel")):
        return "interrupted"
    if any(token in normalized for token in ("失败", "异常", "failed", "error")):
        return "failed"
    if any(token in normalized for token in ("完成", "completed", "success", "done")):
        return "completed"
    if any(token in normalized for token in ("运行", "running")):
        return "running"
    raise ValueError(f"Unknown task status: {status}")


class TaskView(Widget):
    """Render one TaskPresentation without reading pipeline state."""

    def __init__(self, presentation: TaskPresentation) -> None:
        self.presentation = presentation
        self.kind = _status_kind(presentation.status)
        super().__init__(id="task-view")

    def compose(self) -> ComposeResult:
        with Grid(id="task-grid"):
            yield TaskPipeline(self.presentation)
            with Vertical(id="task-main"):
                yield TaskStatus(self.presentation, self.kind)
                if self.kind == "running":
                    yield ProgressBar(
                        total=100,
                        show_percentage=False,
                        show_eta=False,
                        id="task-progress",
                    )
                    yield Static(
                        f"当前阶段：{self.presentation.stage}",
                        id="task-stage",
                    )
                    log = RichLog(
                        wrap=True,
                        markup=False,
                        auto_scroll=True,
                        min_width=0,
                        id="task-subtitles",
                    )
                    for line in self.presentation.recent_texts:
                        log.write(line)
                    yield log
                elif self.kind == "completed":
                    yield Static("输出", classes="task-label")
                    yield Static(
                        self.presentation.output_text,
                        id="task-output",
                    )
                    yield Static(
                        "动作\n按 O 打开字幕\n按 F 打开所在目录",
                        id="task-actions",
                    )
                elif self.kind == "failed":
                    yield Static("错误摘要", classes="task-label")
                    yield Static(
                        f"{self.presentation.status}\n{self.presentation.output_text}",
                        id="task-error",
                    )
                    yield Static(
                        "下一步\n按 D 打开诊断日志，确认原因后重新运行。",
                        id="task-next-action",
                    )
                else:
                    yield Static("任务已中断", classes="task-label")
                    yield Static(
                        "任务未完成，当前观察结果已保留。",
                        id="task-interrupted-summary",
                    )
                    yield Static(
                        "下一步\n检查保留文件，再重新运行任务。",
                        id="task-next-action",
                    )
                yield TaskDetails(self.presentation)

    def on_mount(self) -> None:
        self._sync_progress()

    def _sync_progress(self) -> None:
        if self.kind == "running":
            progress = self.query_one("#task-progress", ProgressBar)
            if self.presentation.progress is not None:
                progress.update(progress=self.presentation.progress)

    async def update_presentation(self, presentation: TaskPresentation) -> None:
        """Refresh this view without replacing its parent screen."""
        details_collapsed = self.query_one(TaskDetails).collapsed
        previous_log = (
            self.query_one("#task-subtitles", RichLog)
            if self.kind == "running"
            else None
        )
        follow_subtitles = (
            previous_log.is_vertical_scroll_end if previous_log is not None else True
        )
        subtitle_scroll_y = previous_log.scroll_y if previous_log is not None else 0
        self.presentation = presentation
        self.kind = _status_kind(presentation.status)
        await self.recompose()
        self.query_one(TaskDetails).collapsed = details_collapsed
        self._sync_progress()
        if self.kind == "running" and not follow_subtitles:
            self._restore_subtitle_scroll(subtitle_scroll_y)

    def _restore_subtitle_scroll(self, scroll_y: float | int) -> None:
        log = self.query_one("#task-subtitles", RichLog)
        log.auto_scroll = False
        log.scroll_to(y=scroll_y, animate=False, force=True)


class TaskScreen(Screen[None]):
    """Screen seam for embedding a task presentation in the v2 app."""

    HORIZONTAL_BREAKPOINTS = SIGNAL_DESK_BREAKPOINTS

    CSS = """
    TaskScreen {
        align: center top;
    }
    TaskView {
        width: 100%;
        max-width: 104;
        height: 100%;
        padding: 1 2;
    }
    #task-grid {
        width: 100%;
        height: 100%;
        grid-size: 1 2;
        grid-columns: 1fr;
        grid-gutter: 1 2;
    }
    #task-main {
        height: auto;
        min-height: 12;
    }
    #task-status {
        height: auto;
        padding-bottom: 1;
    }
    #task-progress {
        margin-bottom: 1;
    }
    #task-subtitles {
        height: 1fr;
        min-height: 8;
    }
    #task-details {
        height: auto;
        margin-top: 1;
    }
    .task-label {
        padding-top: 1;
    }
    #task-output, #task-error, #task-interrupted-summary, #task-next-action, #task-actions {
        height: auto;
        padding: 1 0;
    }
    TaskScreen.-regular #task-grid,
    TaskScreen.-wide #task-grid {
        grid-size: 2 1;
        grid-columns: 32 1fr;
        height: 1fr;
    }
    TaskScreen.-regular #task-main,
    TaskScreen.-wide #task-main {
        height: 1fr;
    }
    """

    def __init__(self, presentation: TaskPresentation) -> None:
        _status_kind(presentation.status)
        super().__init__()
        self.presentation = presentation

    def compose(self) -> ComposeResult:
        yield TaskView(self.presentation)

    async def update_presentation(self, presentation: TaskPresentation) -> None:
        """Expose the live-observer refresh seam."""
        self.presentation = presentation
        await self.query_one(TaskView).update_presentation(presentation)
