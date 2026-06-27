"""慢速 chunk 检测模块。"""

from __future__ import annotations

from typing import TypedDict


class SlowChunkInfo(TypedDict):
    """慢速 chunk 信息结构。"""

    id: int
    time: float
    avg: float
    threshold: float


class SlowChunkDetector:
    """检测延迟超过阈值倍数的 chunk。"""

    def __init__(self, threshold: float = 1.5):
        self.threshold = threshold
        self._slow_chunks: list[SlowChunkInfo] = []

    def check(self, chunk_latency: float, avg_latency: float) -> bool:
        """检查 chunk 延迟是否超过阈值。"""
        return chunk_latency > avg_latency * self.threshold

    def add_slow_chunk(self, chunk_id: int, latency: float, avg: float) -> None:
        """记录一个慢速 chunk。"""
        self._slow_chunks.append({
            "id": chunk_id,
            "time": latency,
            "avg": avg,
            "threshold": self.threshold,
        })

    def get_slow_chunks(self) -> list[SlowChunkInfo]:
        """获取所有已记录的慢速 chunk。"""
        return self._slow_chunks.copy()
