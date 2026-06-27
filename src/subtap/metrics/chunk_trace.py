"""Chunk-level performance tracing."""

from __future__ import annotations

from collections import deque

from subtap.metrics.events import EventBus, EventType, PipelineEvent


class ChunkTracer:
    """Traces chunk-level performance with sliding window average."""

    def __init__(self, event_bus: EventBus, window_size: int = 10):
        self.event_bus = event_bus
        self._window_size = window_size
        self._chunks: list[dict] = []
        self._latency_window: deque[float] = deque(maxlen=window_size)

    def on_chunk_end(self, event: PipelineEvent) -> None:
        """Record chunk end with sliding window average."""
        chunk_data = event.data
        latency = chunk_data["end_time"] - chunk_data["start_time"]

        # Add to sliding window
        self._latency_window.append(latency)

        # Calculate sliding window average
        avg_latency = sum(self._latency_window) / len(self._latency_window)

        # Record chunk
        self._chunks.append({
            "id": chunk_data["chunk_id"],
            "time": latency,
            "avg": avg_latency,
            "model": chunk_data.get("model", "unknown"),
        })

    def get_slow_chunks(self, threshold: float = 1.5) -> list[dict]:
        """Get chunks exceeding threshold * average latency."""
        if not self._latency_window:
            return []

        avg = sum(self._latency_window) / len(self._latency_window)
        return [
            chunk for chunk in self._chunks
            if chunk["time"] > avg * threshold
        ]
