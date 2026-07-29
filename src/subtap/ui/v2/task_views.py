"""Task state views for TUI v2."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ProgressBar, RichLog, Static
from textual.widget import Widget

from subtap.ui.observer import TaskPresentation, TaskState

from .components import TaskDetails, TaskPipeline, TaskStatus
from .theme import HORIZONTAL_BREAKPOINTS as SIGNAL_DESK_BREAKPOINTS


def _stage_name(stage: str) -> str:
    return {
        "prepare": "音频标准化",
        "chunk": "音频切段",
        "asr": "语音识别",
        "clean": "文本清洗",
        "segment": "智能断句",
        "script_match": "参考文稿匹配",
        "align": "时间轴对齐",
        "hotword": "热词替换",
        "translate": "字幕翻译",
        "learn": "热词学习",
        "export": "字幕导出",
    }.get(stage, "处理阶段")


def _status_kind(state: TaskState) -> str:
    if not isinstance(state, TaskState):
        raise ValueError(f"Unknown task status: {state!r}")
    return state.value


class TaskView(Widget):
    """Render one TaskPresentation without reading pipeline state."""

    def __init__(self, presentation: TaskPresentation) -> None:
        self.presentation = presentation
        self.kind = _status_kind(presentation.state)
        self._rendered_recent_texts: tuple[str, ...] = ()
        self._placeholder_stage: str | None = None
        super().__init__(id="task-view")

    def compose(self) -> ComposeResult:
        yield TaskStatus(self.presentation, self.kind)
        if self.kind == "running":
            with Horizontal(id="task-live-summary"):
                yield Static(
                    f"正在处理  {_stage_name(self.presentation.stage)}",
                    id="task-stage",
                )
                yield Static(
                    f"已完成 {self.presentation.completed_stage_count}/"
                    f"{self.presentation.total_stage_count or '?'} 阶段",
                    id="task-stage-count",
                )
                stage_elapsed = self.presentation.current_stage_elapsed_sec
                elapsed_text = (
                    f"本阶段 {stage_elapsed // 60:02d}:{stage_elapsed % 60:02d}"
                    if stage_elapsed is not None
                    else self.presentation.current_work
                )
                yield Static(elapsed_text, id="task-elapsed")
            yield Static("本阶段进度", id="task-progress-label")
            yield ProgressBar(
                total=100,
                show_percentage=True,
                show_eta=False,
                id="task-progress",
            )
        if self.kind == "running":
            with Grid(id="task-grid"):
                yield TaskPipeline(self.presentation)
                with Vertical(id="task-main"):
                    yield Static("最近字幕", classes="task-label")
                    log = RichLog(
                        wrap=True,
                        markup=False,
                        auto_scroll=True,
                        min_width=0,
                        id="task-subtitles",
                    )
                    if self.presentation.recent_texts:
                        for line in self.presentation.recent_texts:
                            log.write(line)
                    else:
                        log.write(self._waiting_text_for_stage(self.presentation.stage))
                    yield log
                    yield TaskDetails(self.presentation)
        else:
            with Vertical(id="task-terminal"):
                if self.kind == "completed":
                    subtitle_count = (
                        f"字幕 {self.presentation.subtitle_count} 条"
                        if self.presentation.subtitle_count is not None
                        else "字幕数量未记录"
                    )
                    yield Static("输出", classes="task-label")
                    yield Static(self.presentation.output_text, id="task-output")
                    yield Static(
                        f"总耗时 {self.presentation.elapsed_sec // 60:02d}:"
                        f"{self.presentation.elapsed_sec % 60:02d}"
                        f"  ·  {subtitle_count}"
                        f"  ·  {self.presentation.quality_label}",
                        id="task-result-summary",
                    )
                    yield Static(
                        "可打开字幕、打开所在目录，或新建字幕。",
                        id="task-actions",
                    )
                elif self.kind == "failed":
                    yield Static("错误摘要", classes="task-label")
                    yield Static(
                        f"{self.presentation.status}\n{self.presentation.output_text}",
                        id="task-error",
                    )
                    yield Static(
                        f"失败阶段：{self.presentation.failed_stage or '未能确定'}\n"
                        f"原因：{self.presentation.error_message or '请查看诊断日志'}",
                        id="task-failure-reason",
                    )
                    yield Static(
                        "下一步\n打开诊断日志确认原因，或新建字幕。",
                        id="task-next-action",
                    )
                elif self.kind == "interrupted":
                    yield Static("任务已中断", classes="task-label")
                    yield Static(
                        "任务未完成，当前观察结果已保留。",
                        id="task-interrupted-summary",
                    )
                    yield Static(
                        "下一步\n检查保留文件，再新建任务。",
                        id="task-next-action",
                    )
                elif self.kind == "observation_error":
                    yield Static("任务状态未知", classes="task-label")
                    yield Static(
                        "观察日志不完整或与进程结果冲突；最后可信状态已保留。",
                        id="task-error",
                    )
                    yield Static("下一步\n打开诊断日志。", id="task-next-action")
                else:
                    yield Static("历史任务", classes="task-label")
                    yield Static(self.presentation.output_text, id="task-output")
                yield TaskDetails(self.presentation)

    def on_mount(self) -> None:
        self._sync_progress()
        if self.kind == "running":
            self._rendered_recent_texts = self.presentation.recent_texts
            if not self.presentation.recent_texts:
                self._placeholder_stage = self.presentation.stage

    def _sync_progress(self) -> None:
        if self.kind != "running":
            return
        label = self.query_one("#task-progress-label", Static)
        bar = self.query_one("#task-progress", ProgressBar)
        if self.presentation.progress is None:
            label.display = False
            bar.display = False
        else:
            label.display = True
            bar.display = True
            bar.update(progress=self.presentation.progress)

    @staticmethod
    def _requires_recompose(
        previous: TaskPresentation, current: TaskPresentation
    ) -> bool:
        return previous.state is not current.state

    async def update_presentation(self, presentation: TaskPresentation) -> None:
        """Refresh this view without replacing its parent screen."""
        old = self.presentation
        self.presentation = presentation
        self.kind = _status_kind(presentation.state)

        if self._requires_recompose(old, presentation):
            details_collapsed = self.query_one(TaskDetails).collapsed
            previous_log = (
                self.query_one("#task-subtitles", RichLog)
                if old.state is TaskState.RUNNING
                else None
            )
            follow_subtitles = (
                previous_log.is_vertical_scroll_end
                if previous_log is not None
                else True
            )
            subtitle_scroll_y = previous_log.scroll_y if previous_log is not None else 0

            await self.recompose()
            self.query_one(TaskDetails).collapsed = details_collapsed
            self._sync_progress()
            if self.kind == "running" and not follow_subtitles:
                log = self.query_one("#task-subtitles", RichLog)
                log.auto_scroll = False
                log.scroll_to(y=subtitle_scroll_y, animate=False, force=True)
            return

        if self.kind != "running":
            return

        self._update_live_widgets()

    def _update_live_widgets(self) -> None:
        """Update individual widgets without recomposing the full tree."""
        p = self.presentation

        self.query_one(TaskStatus).update_state(p, self.kind)

        self.query_one("#task-stage", Static).update(
            f"正在处理  {_stage_name(p.stage)}"
        )
        self.query_one("#task-stage-count", Static).update(
            f"已完成 {p.completed_stage_count}/{p.total_stage_count or '?'} 阶段"
        )
        elapsed_text = (
            f"本阶段 {p.current_stage_elapsed_sec // 60:02d}:"
            f"{p.current_stage_elapsed_sec % 60:02d}"
            if p.current_stage_elapsed_sec is not None
            else p.current_work
        )
        self.query_one("#task-elapsed", Static).update(elapsed_text)

        self._sync_progress()
        self._update_subtitles()
        self.query_one(TaskPipeline).update_state(p)

        details = self.query_one(TaskDetails)
        if not details.collapsed:
            details._update_content(p)

    @staticmethod
    def _waiting_text_for_stage(stage: str) -> str:
        return {
            "prepare": "正在准备音频…",
            "chunk": "正在分析并切分音频…",
            "asr": "正在识别，首段字幕生成后将在这里显示…",
            "align": "正在对齐字幕时间轴…",
        }.get(stage, "正在处理当前阶段…")

    def _update_subtitles(self) -> None:
        """Append only new subtitle texts to the RichLog, managing placeholder state."""
        if not self._is_mounted:
            return
        log = self.query_one("#task-subtitles", RichLog)
        new = self.presentation.recent_texts
        was_at_end = log.is_vertical_scroll_end

        if not was_at_end:
            log.auto_scroll = False

        if new:
            # Real subtitles available: clear placeholder if showing, then append new
            old = self._rendered_recent_texts
            if not old or self._placeholder_stage is not None:
                log.clear()
                self._placeholder_stage = None
                additions = new
            elif len(new) >= len(old) and new[: len(old)] == old:
                additions = new[len(old) :]
            else:
                log.clear()
                additions = new
            for text in additions:
                log.write(text)
            self._rendered_recent_texts = new
        else:
            # No subtitles: show placeholder for current stage
            current_stage = self.presentation.stage
            if self._placeholder_stage != current_stage:
                log.clear()
                log.write(self._waiting_text_for_stage(current_stage))
                self._placeholder_stage = current_stage
            self._rendered_recent_texts = ()


class TaskScreen(Screen[None]):
    """Screen seam for embedding a task presentation in the v2 app."""

    HORIZONTAL_BREAKPOINTS = SIGNAL_DESK_BREAKPOINTS

    DEFAULT_CSS = """
    TaskScreen {
        align: center top;
    }
    TaskView {
        width: 100%;
        max-width: 104;
        height: 100%;
        padding: 2 3 1 3;
    }
    #task-status {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        background: $surface;
        color: $primary;
        text-style: bold;
    }
    #task-live-summary {
        height: 3;
        padding: 0 1;
    }
    #task-stage {
        width: 1fr;
        height: auto;
        text-style: bold;
    }
    #task-stage-count {
        width: auto;
        height: auto;
        margin-right: 2;
        color: $text-muted;
    }
    #task-elapsed {
        width: auto;
        height: auto;
        color: $text-muted;
    }
    #task-progress {
        margin: 0 1 1 1;
    }
    #task-progress-label {
        height: auto;
        margin: 0 1 1 1;
        color: $text-muted;
    }
    #task-grid {
        width: 100%;
        height: auto;
        grid-size: 1 2;
        grid-columns: 1fr;
        grid-gutter: 1 2;
    }
    #task-terminal {
        height: auto;
        min-height: 14;
        padding: 2 3;
        background: $surface;
    }
    #task-pipeline, #task-main {
        padding: 1 2;
    }
    #task-pipeline {
        height: auto;
    }
    #task-main {
        height: auto;
        min-height: 12;
    }
    #task-subtitles {
        height: 12;
        min-height: 6;
    }
    #task-details {
        height: auto;
        margin-top: 1;
    }
    .task-label {
        padding-top: 1;
    }
    #task-output, #task-error, #task-failure-reason, #task-interrupted-summary,
    #task-next-action, #task-actions, #task-result-summary {
        height: auto;
        padding: 1 0;
    }
    TaskScreen.-regular #task-grid,
    TaskScreen.-wide #task-grid {
        grid-size: 2 1;
        grid-columns: 32 1fr;
    }
    TaskScreen.-compact #task-pipeline {
        display: none;
    }
    TaskScreen.-compact #task-main {
        min-height: 8;
    }
    TaskScreen.-compact #task-subtitles {
        height: 8;
        min-height: 4;
    }
    """

    def __init__(self, presentation: TaskPresentation) -> None:
        _status_kind(presentation.state)
        super().__init__()
        self.presentation = presentation

    def compose(self) -> ComposeResult:
        yield TaskView(self.presentation)

    async def update_presentation(self, presentation: TaskPresentation) -> None:
        """Expose the live-observer refresh seam."""
        self.presentation = presentation
        await self.query_one(TaskView).update_presentation(presentation)

    def action_new_task(self) -> None:
        from .new_transcription import NewTranscriptionScreen

        self.app.push_screen(NewTranscriptionScreen(), self._finish_new_task)

    def _finish_new_task(self, command: list[str] | None) -> None:
        if command is None:
            return
        start_transcription = getattr(self.app, "start_transcription", None)
        if start_transcription is None:
            raise RuntimeError("当前应用无法启动转录任务")
        start_transcription(command)
