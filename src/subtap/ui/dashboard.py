"""Textual 仪表板，用于管道执行监控。"""

from __future__ import annotations

import asyncio
import time

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ProgressBar

from subtap.metrics.events import EventBus
from subtap.metrics.profiler import PipelineProfiler

# 中文阶段名称映射
STAGE_CN = {
    "prepare": "音频标准化",
    "chunk": "音频切段",
    "asr": "语音识别",
    "clean": "文本优化",
    "segment": "智能断句",
    "align": "字幕对齐",
    "export": "字幕导出",
}


class StagePanel(Static):
    """当前阶段显示。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stage = "等待中"

    def update_stage(self, stage: str) -> None:
        """更新当前阶段。"""
        self._stage = STAGE_CN.get(stage, stage)
        self.update(f"当前阶段：{self._stage}")


class ProgressPanel(Static):
    """进度显示。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._progress = 0

    def update_progress(self, progress: int) -> None:
        """更新进度百分比。"""
        self._progress = progress
        bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
        self.update(f"进度：{bar} {progress}%")


class ChunkPanel(Static):
    """Chunk 进度显示。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current = 0
        self._total = 0

    def update_chunk(self, current: int, total: int) -> None:
        """更新 chunk 进度。"""
        self._current = current
        self._total = total
        self.update(f"当前 Chunk：{current} / {total}")


class ModelPanel(Static):
    """模型信息显示。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = "未知"
        self._latency = 0.0

    def update_model(self, model: str, latency: float) -> None:
        """更新模型信息。"""
        self._model = model
        self._latency = latency
        self.update(f"当前模型：{self._model}\n延迟：{latency:.2f}s / chunk")


class PipelineDashboard(App):
    """Textual 仪表板，用于管道执行监控。"""

    def __init__(self, event_bus: EventBus, profiler: PipelineProfiler, **kwargs):
        super().__init__(**kwargs)
        self.event_bus = event_bus
        self.profiler = profiler
        self._update_throttle = 0.05  # 50ms 节流
        self._last_update = 0

    def _should_update(self) -> bool:
        """检查是否应该更新（节流）。"""
        now = time.monotonic()
        if now - self._last_update < self._update_throttle:
            return False
        self._last_update = now
        return True

    def compose(self) -> ComposeResult:
        yield Header()
        yield StagePanel()
        yield ProgressPanel()
        yield ChunkPanel()
        yield ModelPanel()
        yield Footer()

    async def on_mount(self) -> None:
        """启动事件处理。"""
        self.run_worker(self.event_bus.start())

    def update_stage(self, stage: str) -> None:
        """更新阶段显示。"""
        if not self._should_update():
            return
        stage_panel = self.query_one(StagePanel)
        stage_panel.update_stage(stage)

    def update_progress(self, progress: int) -> None:
        """更新进度显示。"""
        progress = max(0, min(100, progress))  # 限制在 0-100 范围
        if not self._should_update():
            return
        progress_panel = self.query_one(ProgressPanel)
        progress_panel.update_progress(progress)

    def update_chunk(self, current: int, total: int) -> None:
        """更新 chunk 显示。"""
        if not self._should_update():
            return
        chunk_panel = self.query_one(ChunkPanel)
        chunk_panel.update_chunk(current, total)

    def update_model(self, model: str, latency: float) -> None:
        """更新模型显示。"""
        if not self._should_update():
            return
        model_panel = self.query_one(ModelPanel)
        model_panel.update_model(model, latency)
