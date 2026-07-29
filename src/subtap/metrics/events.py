"""Event system for pipeline metrics."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


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
    PIPELINE_PLAN = "pipeline_plan"
    PIPELINE_END = "pipeline_end"


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
    total_duration_sec: float | None = None,
    model: str | None = None,
    text: str | None = None,
    item_index: int | None = None,
    total_items: int | None = None,
    stages: list[str] | None = None,
    status: str | None = None,
    output_ready: bool | None = None,
    subtitle_count: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    message_zh: str = "",
) -> PipelineEvent:
    """Build a streaming event with the shared payload contract."""
    if not task_id.strip():
        raise ValueError("task_id must not be blank")
    if not stage.strip():
        raise ValueError("stage must not be blank")
    if event_type is EventType.STAGE_END:
        if status is None:
            raise ValueError("stage_end requires status")
        if duration_sec is None:
            raise ValueError("stage_end requires duration_sec")
    elif event_type is EventType.PIPELINE_PLAN and not stages:
        raise ValueError("pipeline_plan requires stages")
    elif event_type is EventType.PIPELINE_END:
        if status is None:
            raise ValueError("pipeline_end requires status")
        if total_duration_sec is None:
            raise ValueError("pipeline_end requires total_duration_sec")
        if output_ready is None:
            raise ValueError("pipeline_end requires output_ready")
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
        "total_duration_sec": total_duration_sec,
        "model": model,
        "text": text,
        "item_index": item_index,
        "total_items": total_items,
        "stages": stages,
        "status": status,
        "output_ready": output_ready,
        "subtitle_count": subtitle_count,
        "error_code": error_code,
        "error_message": error_message,
    }
    for key, value in optional.items():
        if value is not None:
            data[key] = value
    return PipelineEvent(event_type=event_type, data=data, timestamp=timestamp)


class EventBus:
    """Async event bus with queue buffer."""

    def __init__(self, buffer_size: int = 100, log_path: Path | None = None):
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=buffer_size)
        self._running = False
        self._stop_event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread_id: int | None = None
        self._log_path = log_path

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
        self._write_log(event)
        if self._is_running_on_other_thread() and self._loop is not None:
            self._loop.call_soon_threadsafe(self._enqueue_nowait, event)
            return
        self._enqueue_nowait(event)

    def _write_log(self, event: PipelineEvent) -> None:
        if self._log_path is None:
            return
        run_id = event.data.get("task_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("schema v2 event log requires a non-empty task_id")
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "run_id": run_id,
            "event_type": event.event_type.value,
            "timestamp": event.timestamp,
            "data": event.data,
        }
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _enqueue_nowait(self, event: PipelineEvent) -> None:
        """Enqueue without blocking the caller."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error(
                "事件队列已满，事件未进入订阅分发：%s",
                event.event_type.value,
            )

    def _is_running_on_other_thread(self) -> bool:
        return (
            self._loop is not None
            and self._loop.is_running()
            and self._loop_thread_id is not None
            and threading.get_ident() != self._loop_thread_id
        )

    async def start(self) -> None:
        """Start event processing loop."""
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._loop_thread_id = threading.get_ident()
        self._stop_event.clear()
        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                    await self._dispatch(event)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
        finally:
            self._loop = None
            self._loop_thread_id = None

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
