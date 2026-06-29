"""Textual 仪表板，用于管道执行监控。"""

from __future__ import annotations

import time
from collections.abc import Callable

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static

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


class StatsPanel(Static):
    """字幕和性能摘要。"""

    def update_stats(
        self, streaming: dict[str, object], performance: dict[str, object]
    ) -> None:
        preview = str(streaming.get("preview") or "")
        if len(preview) > 28:
            preview = preview[:28] + "..."
        self.update(
            "候选字幕：{candidate}  已对齐：{aligned}\n"
            "RTF：{rtf:.2f}  慢速片段：{slow}\n"
            "预览：{preview}".format(
                candidate=int(streaming.get("candidate_count") or 0),
                aligned=int(streaming.get("aligned_count") or 0),
                rtf=float(performance.get("rtf") or 0.0),
                slow=int(performance.get("slow_chunks_total") or 0),
                preview=preview or "暂无",
            )
        )


class PipelineDashboard(App):
    """Textual 仪表板，用于管道执行监控。"""

    def __init__(self, event_bus: EventBus, profiler: PipelineProfiler, **kwargs):
        super().__init__(**kwargs)
        self.event_bus = event_bus
        self.profiler = profiler
        self._update_throttle = 0.05  # 50ms 节流
        self._last_update = 0.0
        self.streaming_state: dict[str, object] = {
            "stage": "等待中",
            "chunk_id": None,
            "candidate_count": 0,
            "aligned_count": 0,
            "model": "未知",
            "preview": "",
        }
        self.performance_state: dict[str, object] = {
            "rtf": 0.0,
            "total_runtime_sec": 0.0,
            "asr_runtime_sec": 0.0,
            "align_runtime_sec": 0.0,
            "enhancement_runtime_sec": 0.0,
            "slow_chunks_total": 0,
            "model": "未知",
            "quantization": "未知",
        }
        self._startup_callback: Callable[[], None] | None = None

    def set_startup_callback(self, callback: Callable[[], None]) -> None:
        """设置 TUI mount 后启动的后台任务。"""
        self._startup_callback = callback

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
        yield StatsPanel()
        yield Footer()

    async def on_mount(self) -> None:
        """启动事件处理。"""
        self.run_worker(self.event_bus.start())
        if self._startup_callback is not None:
            self._startup_callback()

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

    def update_stage_complete(self, stage: str, duration: float) -> None:
        """更新阶段完成状态。"""
        if stage == "export":
            self.query_one(StagePanel).update("当前阶段：全流程完成")
            self.query_one(ProgressPanel).update_progress(100)
            self._refresh_stats()
            self.exit()

    def _refresh_stats(self) -> None:
        """刷新字幕和性能摘要。"""
        try:
            self.query_one(StatsPanel).update_stats(
                self.streaming_state, self.performance_state
            )
        except Exception:
            return

    def update_streaming_event(self, data: dict) -> None:
        """消费字幕生产事件，更新阶段、进度、模型和计数状态。"""

        def _counter(name: str) -> int:
            value = self.streaming_state.get(name, 0)
            return int(value) if isinstance(value, (int, float, str)) else 0

        self.streaming_state.update(
            {
                "stage": data.get("stage", self.streaming_state["stage"]),
                "chunk_id": data.get("chunk_id", self.streaming_state["chunk_id"]),
                "model": data.get("model", self.streaming_state["model"]),
                "preview": data.get("text", self.streaming_state["preview"]),
            }
        )
        if data.get("stage") == "segment":
            self.streaming_state["candidate_count"] = _counter("candidate_count") + 1
        if data.get("stage") == "align":
            self.streaming_state["aligned_count"] = _counter("aligned_count") + 1
        if not self._should_update():
            return
        if "stage" in data:
            self.query_one(StagePanel).update_stage(str(data["stage"]))
        if "progress" in data:
            self.query_one(ProgressPanel).update_progress(int(data["progress"]))
        if "model" in data:
            self.query_one(ModelPanel).update_model(
                str(data["model"]), float(data.get("duration_sec", 0.0))
            )
        self._refresh_stats()

    def update_performance_metrics(self, metrics: dict) -> None:
        """更新 TUI 性能状态，供性能面板显示。"""
        self.performance_state.update(
            {
                "rtf": metrics.get("rtf", 0.0),
                "total_runtime_sec": metrics.get("total_runtime_sec", 0.0),
                "asr_runtime_sec": metrics.get("asr_runtime_sec", 0.0),
                "align_runtime_sec": metrics.get("align_runtime_sec", 0.0),
                "enhancement_runtime_sec": metrics.get("enhancement_runtime_sec", 0.0),
                "slow_chunks_total": len(metrics.get("slow_chunks", [])),
                "model": metrics.get("asr_model", "未知"),
                "quantization": metrics.get("quantization", "未知"),
            }
        )
        self._refresh_stats()
