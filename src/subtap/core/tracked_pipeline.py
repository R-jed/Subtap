"""TrackedPipeline: Pipeline with state persistence for crash recovery."""

from __future__ import annotations

import logging
from pathlib import Path

from subtap.core.pipeline import Pipeline
from subtap.engine.state import (
    CheckpointPersistenceError,
    PipelineRunContext,
    PipelineState,
)
from subtap.runtime.external_policy import ExternalProcessingPolicy

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
        stage_order: list[str] | None = None,
        external_policy: ExternalProcessingPolicy | None = None,
    ):
        super().__init__(
            config,
            work_dir,
            event_bus=event_bus,
            task_id=task_id,
            external_policy=external_policy,
        )
        if state is not None:
            self.state = state
        elif stage_order is not None:
            self.state = PipelineState.new(stage_order)
        else:
            self.state = PipelineState()
        self._state_path = self.workspace.root / STATE_FILE
        # Transitional compatibility mirrors — derived from authoritative policy
        if external_policy is not None:
            self._local_only: bool = external_policy.local_only
            self._policy_mode: str = external_policy.enhance_mode.value
        else:
            self._local_only = False
            self._policy_mode = "local"

    def save_state(self) -> None:
        """Atomically persist current state to disk.

        Raises CheckpointPersistenceError on failure -- a checkpoint write
        failure means execution state is no longer reliable, so the stage
        must not continue.
        """
        try:
            self.state.save(self._state_path)
        except Exception as exc:
            raise CheckpointPersistenceError(
                "failed to persist pipeline checkpoint"
            ) from exc

    def set_stage_plan(
        self,
        stage_keys: list[str],
        context: PipelineRunContext | None = None,
    ) -> None:
        """Set the dynamic stage plan from the runner.

        Creates a fresh PipelineState with the exact stage list for this run,
        so that pipeline-state.json reflects the real execution plan.
        """
        self.state = PipelineState.new(stage_order=stage_keys, context=context)
        self._state_path = self.workspace.root / STATE_FILE
        self.save_state()

    def run_stage(self, stage: str, **kwargs) -> dict:
        """Run stage with state persistence.

        Only stages present in PipelineState (the core pipeline stages)
        are tracked.  Optional stages (hotword, learn, script_match,
        translate) run without persistence.

        For external-capable stages, the missing-policy guard must fire
        BEFORE any state mutation so that checkpoint files never record
        a RUNNING/FAILED state for a stage that was rejected by policy.

        SUCCESS checkpoint is persisted OUTSIDE the business exception
        handler so that a checkpoint failure raises CheckpointPersistenceError
        rather than being mistaken for a stage failure.
        """
        # Preflight: delegate missing-policy rejection to the authoritative
        # Pipeline guard before any checkpoint mutation.
        if stage in self._EXTERNAL_CAPABLE_STAGES and self.external_policy is None:
            return super().run_stage(stage, **kwargs)

        tracked = stage in self.state.stages
        if tracked:
            self.state.mark_running(stage)
            self.save_state()

        try:
            result = super().run_stage(stage, **kwargs)
        except Exception as e:
            if tracked:
                self.state.mark_failed(stage, str(e))
                self.save_state()
            raise

        if tracked:
            self.state.mark_success(stage, result, 0.0)
            self.save_state()

        return result
