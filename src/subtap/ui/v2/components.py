"""Small Textual components shared by the v2 task states."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from subtap.ui.observer import TaskPresentation


class PageHeader(Widget):
    """Shared title and one-sentence orientation for secondary pages."""

    def __init__(self, title: str, description: str) -> None:
        super().__init__(classes="page-header")
        self.title = title
        self.description = description

    def compose(self) -> ComposeResult:
        yield Static(self.title, classes="desk-title")
        yield Static(self.description, classes="desk-copy")


class TaskStatus(Static):
    """Status text whose label remains meaningful without color."""

    def __init__(self, presentation: TaskPresentation, kind: str) -> None:
        super().__init__(id="task-status")
        self.update_state(presentation, kind)

    def update_state(self, presentation: TaskPresentation, kind: str) -> None:
        label = {
            "running": "运行中",
            "completed": "已完成",
            "failed": "失败",
            "interrupted": "已中断",
            "recorded": "任务记录",
            "observation_error": "状态未知",
        }[kind]
        self.update(f"状态：{label} · {presentation.status}")


class TaskPipeline(Static):
    """Pipeline navigation rendered from the reducer presentation."""

    def __init__(self, presentation: TaskPresentation) -> None:
        super().__init__(id="task-pipeline")
        self.update_state(presentation)

    def update_state(self, presentation: TaskPresentation) -> None:
        content = "[b]处理流程[/b]\n" + (
            "\n".join(presentation.stage_lines)
            if presentation.stage_lines
            else "等待任务公布处理流程…"
        )
        self.update(content)


class TaskDetails(Collapsible):
    """P2 task metadata kept behind an explicit Details disclosure."""

    def __init__(self, presentation: TaskPresentation) -> None:
        self._static = Static("")
        super().__init__(
            self._static,
            title="详情",
            collapsed=True,
            id="task-details",
        )
        self._update_content(presentation)

    def _update_content(self, presentation: TaskPresentation) -> None:
        content = "\n".join(
            (
                f"当前阶段：{presentation.stage}",
                f"当前模型：{presentation.model}",
                presentation.counts,
                presentation.current_work,
                f"总用时：{presentation.elapsed_sec // 60:02d}:{presentation.elapsed_sec % 60:02d}",
                "",
                "处理流程",
                *presentation.stage_lines,
                "隐私：观察者只读取本地日志，不接触音频和模型推理",
            )
        )
        self._static.update(content)
