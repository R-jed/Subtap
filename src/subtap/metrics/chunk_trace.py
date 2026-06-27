"""分块级别的性能追踪。"""

from __future__ import annotations

from collections import deque

from subtap.metrics.events import EventBus, PipelineEvent


class ChunkTracer:
    """分块级别性能追踪，支持滑动窗口平均值计算。"""

    def __init__(self, event_bus: EventBus, window_size: int = 10):
        self.event_bus = event_bus
        self._window_size = window_size
        self._chunks: list[dict] = []
        self._latency_window: deque[float] = deque(maxlen=window_size)

    def on_chunk_end(self, event: PipelineEvent) -> None:
        """记录分块结束事件，计算滑动窗口平均值。"""
        chunk_data = event.data
        latency = chunk_data.get("end_time", 0) - chunk_data.get("start_time", 0)

        # 添加到滑动窗口
        self._latency_window.append(latency)

        # 计算滑动窗口平均值
        avg_latency = sum(self._latency_window) / len(self._latency_window)

        # 记录分块数据
        self._chunks.append(
            {
                "id": chunk_data.get("chunk_id", "unknown"),
                "time": latency,
                "avg": avg_latency,
                "model": chunk_data.get("model", "unknown"),
            }
        )

    def get_slow_chunks(self, threshold: float = 1.5) -> list[dict]:
        """获取超过阈值倍平均延迟的分块。"""
        if not self._chunks:
            return []

        # 使用最近一次计算的平均值
        avg = self._chunks[-1]["avg"]
        return [chunk for chunk in self._chunks if chunk["time"] > avg * threshold]
