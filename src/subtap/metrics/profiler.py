"""Pipeline performance profiler."""

from __future__ import annotations

import time
from typing import Any

from subtap.metrics.events import EventBus, EventType, make_pipeline_event


class PipelineProfiler:
    """Profiles pipeline execution with stage and chunk timing."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._stage_times: dict[str, float] = {}

    def wrap_pipeline(self, pipeline: Any) -> None:
        """Wrap pipeline.run_stage with profiling."""
        original_run_stage = pipeline.run_stage
        task_id = getattr(pipeline, "task_id", "local")

        def publish(event_type: EventType, stage: str, **data: Any) -> None:
            self.event_bus.publish_nowait(
                make_pipeline_event(
                    event_type,
                    task_id=task_id,
                    stage=stage,
                    **data,
                )
            )

        def wrapped_run_stage(stage_name: str, **kwargs) -> Any:
            publish(
                EventType.STAGE_START,
                stage_name,
                message_zh="阶段开始",
            )

            stage_start = time.monotonic()
            try:
                result = original_run_stage(stage_name, **kwargs)
            except Exception:
                duration = time.monotonic() - stage_start
                publish(
                    EventType.STAGE_END,
                    stage_name,
                    duration_sec=duration,
                    status="failed",
                    message_zh="阶段失败",
                )
                raise
            duration = time.monotonic() - stage_start
            self._stage_times[stage_name] = duration
            publish(
                EventType.STAGE_END,
                stage_name,
                duration_sec=duration,
                status="success",
                message_zh="阶段完成",
            )

            return result

        # Mark as wrapped for testing.
        setattr(wrapped_run_stage, "__wrapped__", original_run_stage)
        pipeline.run_stage = wrapped_run_stage

    def get_report(self) -> dict:
        """Generate performance report."""
        return {
            "total_time": sum(self._stage_times.values()),
            "stages": self._stage_times,
        }
