"""事件桥接，连接指标系统到 UI。"""

from __future__ import annotations

from typing import Any

from subtap.metrics.events import EventBus, EventType, PipelineEvent


class EventBridge:
    """桥接管道事件到仪表板更新。"""

    def __init__(self, event_bus: EventBus, dashboard: Any):
        self.event_bus = event_bus
        self.dashboard = dashboard

    def connect(self) -> None:
        """连接事件到 UI 更新。"""
        self.event_bus.subscribe(EventType.STAGE_START, self._on_stage_start)
        self.event_bus.subscribe(EventType.STAGE_END, self._on_stage_end)
        self.event_bus.subscribe(EventType.CHUNK_END, self._on_chunk_end)
        self.event_bus.subscribe(EventType.PROGRESS, self._on_progress)

    def _on_stage_start(self, event: PipelineEvent) -> None:
        """处理阶段开始事件。"""
        if self.dashboard and hasattr(self.dashboard, 'update_stage'):
            self.dashboard.update_stage(event.data["stage"])

    def _on_stage_end(self, event: PipelineEvent) -> None:
        """处理阶段结束事件。"""
        if self.dashboard and hasattr(self.dashboard, 'update_stage_complete'):
            self.dashboard.update_stage_complete(
                event.data["stage"],
                event.data["duration"]
            )

    def _on_chunk_end(self, event: PipelineEvent) -> None:
        """处理 chunk 结束事件。"""
        if self.dashboard and hasattr(self.dashboard, 'update_chunk'):
            self.dashboard.update_chunk(event.data)

    def _on_progress(self, event: PipelineEvent) -> None:
        """处理进度事件。"""
        if self.dashboard and hasattr(self.dashboard, 'update_progress'):
            self.dashboard.update_progress(event.data)
