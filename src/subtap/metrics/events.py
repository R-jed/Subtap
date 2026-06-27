"""Event system for pipeline metrics."""

from __future__ import annotations

import asyncio
import inspect
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


@dataclass
class PipelineEvent:
    """Pipeline event data."""

    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


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
