"""Slow chunk detection."""

from __future__ import annotations


class SlowChunkDetector:
    """Detects chunks with latency exceeding threshold * average."""

    def __init__(self, threshold: float = 1.5):
        self.threshold = threshold
        self._slow_chunks: list[dict] = []

    def check(self, chunk_latency: float, avg_latency: float) -> bool:
        """Check if chunk latency exceeds threshold."""
        return chunk_latency > avg_latency * self.threshold

    def add_slow_chunk(self, chunk_id: int, latency: float, avg: float) -> None:
        """Record a slow chunk."""
        self._slow_chunks.append({
            "id": chunk_id,
            "time": latency,
            "avg": avg,
            "threshold": self.threshold,
        })

    def get_slow_chunks(self) -> list[dict]:
        """Get all recorded slow chunks."""
        return self._slow_chunks
