"""Small Textual components shared by the v2 task states."""

from __future__ import annotations

from textual.widgets import Collapsible, Static

from subtap.ui.observer import TaskPresentation


class TaskStatus(Static):
    """Status text whose label remains meaningful without color."""

    def __init__(self, presentation: TaskPresentation, kind: str) -> None:
        label = {
            "running": "运行中",
            "completed": "已完成",
            "failed": "失败",
            "interrupted": "已中断",
        }[kind]
        super().__init__(f"状态：{label} · {presentation.status}", id="task-status")


class TaskPipeline(Static):
    """Pipeline navigation rendered from the reducer presentation."""

    def __init__(self, presentation: TaskPresentation) -> None:
        content = "[b]处理流程[/b]\n" + "\n".join(presentation.stage_lines)
        super().__init__(content, id="task-pipeline")


class TaskDetails(Collapsible):
    """P2 task metadata kept behind an explicit Details disclosure."""

    def __init__(self, presentation: TaskPresentation) -> None:
        content = "\n".join(
            (
                f"当前阶段：{presentation.stage}",
                f"当前模型：{presentation.model}",
                presentation.counts,
                presentation.current_work,
                "隐私：观察者只读取本地日志，不接触音频和模型推理",
            )
        )
        super().__init__(
            Static(content),
            title="详情",
            collapsed=True,
            id="task-details",
        )
