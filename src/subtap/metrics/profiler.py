"""Pipeline performance profiler."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from subtap.metrics.events import EventBus, EventType, PipelineEvent


class PipelineProfiler:
    """Profiles pipeline execution with stage and chunk timing."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._stage_times: dict[str, float] = {}

    def wrap_pipeline(self, pipeline: Any) -> None:
        """Wrap pipeline.run_stage with profiling."""
        original_run_stage = pipeline.run_stage

        def wrapped_run_stage(stage_name: str, **kwargs) -> Any:
            # Publish stage start event
            asyncio.create_task(self.event_bus.publish(PipelineEvent(
                event_type=EventType.STAGE_START,
                data={"stage": stage_name},
                timestamp=time.time()
            )))

            stage_start = time.time()
            result = original_run_stage(stage_name, **kwargs)
            stage_end = time.time()

            # Record stage time
            self._stage_times[stage_name] = stage_end - stage_start

            # Publish stage end event
            asyncio.create_task(self.event_bus.publish(PipelineEvent(
                event_type=EventType.STAGE_END,
                data={"stage": stage_name, "duration": stage_end - stage_start},
                timestamp=time.time()
            )))

            return result

        # Mark as wrapped for testing
        wrapped_run_stage.__wrapped__ = True
        pipeline.run_stage = wrapped_run_stage

    def get_report(self) -> dict:
        """Generate performance report."""
        return {
            "total_time": sum(self._stage_times.values()),
            "stages": self._stage_times,
        }
