"""TrackedPipeline: Pipeline with state persistence for crash recovery."""

from __future__ import annotations

import logging
from pathlib import Path

from subtap.core.pipeline import Pipeline
from subtap.engine.state import PipelineState

logger = logging.getLogger(__name__)

STATE_FILE = "pipeline-state.json"


class TrackedPipeline(Pipeline):
    """Pipeline that persists stage state to disk.

    Wraps run_stage() to call mark_running/mark_success/mark_failed + save,
    so that pipeline-state.json always reflects the real execution state.
    After a crash (os._exit, SIGKILL, etc.), the state file retains the
    last persisted RUNNING checkpoint for resume.
    """

    def __init__(
        self,
        config,
        work_dir: Path,
        event_bus=None,
        task_id: str = "local",
        state: PipelineState | None = None,
    ):
        super().__init__(config, work_dir, event_bus=event_bus, task_id=task_id)
        self.state = state or PipelineState()
        self._state_path = self.workspace.root / STATE_FILE

    def save_state(self) -> None:
        """Atomically persist current state to disk."""
        try:
            self.state.save(self._state_path)
        except Exception as e:
            logger.warning("Failed to save pipeline state: %s", e)

    def run_stage(self, stage: str, **kwargs) -> dict:
        """Run stage with state persistence.

        Only stages present in PipelineState (the core pipeline stages)
        are tracked.  Optional stages (hotword, learn, script_match,
        translate) run without persistence.
        """
        tracked = stage in self.state.stages
        if tracked:
            self.state.mark_running(stage)
            self.save_state()
        try:
            result = super().run_stage(stage, **kwargs)
            if tracked:
                self.state.mark_success(stage, result, 0.0)
                self.save_state()
            return result
        except Exception as e:
            if tracked:
                self.state.mark_failed(stage, str(e))
                self.save_state()
            raise
