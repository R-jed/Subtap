"""Event system for pipeline metrics."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
    """Pipeline event types."""

    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    CHUNK_START = "chunk_start"
    CHUNK_END = "chunk_end"
    PROGRESS = "progress"
    MODEL_LOAD = "model_load"
    AUDIO_CHUNK_READY = "audio_chunk_ready"
    ASR_DRAFT_READY = "asr_draft_ready"
    ENHANCEMENT_READY = "enhancement_ready"
    SENTENCE_CANDIDATE_READY = "sentence_candidate_ready"
    ALIGNMENT_READY = "alignment_ready"
    SUBTITLE_PREVIEW_READY = "subtitle_preview_ready"
    MODEL_LOAD_START = "model_load_start"
    MODEL_LOAD_DONE = "model_load_done"
    MODEL_RELEASE_START = "model_release_start"
    MODEL_RELEASE_DONE = "model_release_done"


@dataclass
class PipelineEvent:
    """Pipeline event data."""

    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


def make_pipeline_event(
    event_type: EventType,
    *,
    task_id: str,
    stage: str,
    chunk_id: int | None = None,
    segment_id: int | None = None,
    subtitle_id: int | None = None,
    progress: int | float | None = None,
    duration_sec: float | None = None,
    model: str | None = None,
    message_zh: str = "",
) -> PipelineEvent:
    """Build a streaming event with the shared payload contract."""
    timestamp = time.time()
    data: dict[str, Any] = {
        "task_id": task_id,
        "stage": stage,
        "timestamp": timestamp,
        "message_zh": message_zh,
    }
    optional = {
        "chunk_id": chunk_id,
        "segment_id": segment_id,
        "subtitle_id": subtitle_id,
        "progress": progress,
        "duration_sec": duration_sec,
        "model": model,
    }
    for key, value in optional.items():
        if value is not None:
            data[key] = value
    return PipelineEvent(event_type=event_type, data=data, timestamp=timestamp)


class EventBus:
    """Async event bus with queue buffer."""

    def __init__(self, buffer_size: int = 100):
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=buffer_size)
        self._running = False
        self._stop_event = asyncio.Event()

    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        """Subscribe to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    async def publish(self, event: PipelineEvent) -> None:
        """Non-blocking publish to queue."""
        self.publish_nowait(event)

    def publish_nowait(self, event: PipelineEvent) -> None:
        """Publish from synchronous code without requiring a running loop."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # 丢弃新事件以防止阻塞

    async def start(self) -> None:
        """Start event processing loop."""
        self._running = True
        self._stop_event.clear()
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _dispatch(self, event: PipelineEvent) -> None:
        """Dispatch event to subscribers."""
        import logging

        for callback in self._subscribers.get(event.event_type, []):
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logging.getLogger(__name__).error(f"Event callback error: {e}")

    def stop(self) -> None:
        """Stop event processing loop."""
        self._running = False
        self._stop_event.set()
