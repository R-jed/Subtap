"""PipelineController: state-machine driven pipeline execution with retry, skip, resume."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Optional

from subtap.engine.state import (
    PipelineState,
    PipelineRunContext,
    StageStatus,
    STATUS_CN,
    STAGE_ORDER,
    build_stage_kwargs,
)
from subtap.engine.policy import ExecutionPolicy
from subtap.engine.events import EventLogger
from subtap.schemas.config import SubtapConfig
from subtap.core.workspace import Workspace

logger = logging.getLogger(__name__)

# State file name
STATE_FILE = "pipeline-state.json"


class PipelineController:
    """State-machine driven pipeline execution.

    Supports: run, retry, skip, resume, rollback.
    All state transitions are tracked and persisted.

    Stage execution is unified: normal, resume, and retry all delegate
    to Pipeline._stage_* via TrackedPipeline.run_stage().
    """

    def __init__(
        self,
        config: SubtapConfig,
        work_dir: Path,
        policy: str = "local",
        state: PipelineState | None = None,
    ):
        self.config = config
        self.workspace = Workspace(config, base_dir=work_dir)
        self.policy = ExecutionPolicy(policy)
        self.state = state or PipelineState()
        self.event_log = EventLogger(self.workspace.logs_dir)
        self._on_stage_change: Optional[Callable] = None
        # Pre-flight state (set by CLI before run)
        self._git_commit_hash: str = ""
        self._workspace_clean: bool = True
        # Run context (set before run, persisted with state)
        self._run_context: Optional[PipelineRunContext] = None
        # State file path
        self._state_path = self.workspace.root / STATE_FILE
        # TrackedPipeline (lazily created)
        self._pipeline = None

    def _get_pipeline(self):
        """Get or create TrackedPipeline for stage execution."""
        if self._pipeline is None:
            from subtap.core.tracked_pipeline import TrackedPipeline

            self._pipeline = TrackedPipeline(
                self.config,
                work_dir=self.workspace.root,
                state=self.state,
            )
        return self._pipeline

    def load_state(self) -> None:
        """Load persisted state from _state_path.

        Raises:
            FileNotFoundError: if state file does not exist.
            ValueError: if state file is corrupt or has invalid schema.
        """
        self.state = PipelineState.load(self._state_path)
        # Reset pipeline so it gets the new state
        self._pipeline = None

    def set_preflight_state(
        self, git_commit_hash: str = "", workspace_clean: bool = True
    ) -> None:
        """Set pre-flight state for event logging."""
        self._git_commit_hash = git_commit_hash
        self._workspace_clean = workspace_clean

    def set_context(self, ctx: PipelineRunContext) -> None:
        """Restore run context from persisted state for resume/retry.

        Updates config so Pipeline._stage_* methods use persisted values.
        """
        self._run_context = ctx
        # Update config so stage handlers use persisted values
        if ctx.script_path:
            self.config.output.script_path = ctx.script_path
        if ctx.script_mode:
            self.config.output.script_mode = ctx.script_mode
        if ctx.subtitle_language:
            self.config.output.subtitle_language = ctx.subtitle_language
        if ctx.max_chars:
            self.config.output.max_chars = ctx.max_chars
        self.config.output.subtitle_punctuation = ctx.subtitle_punctuation
        if ctx.subtitle_stem:
            self.config.output.subtitle_stem = ctx.subtitle_stem
        if ctx.glossary_path:
            self.config.clean.glossary_path = ctx.glossary_path

    def _restore_context_from_state(self) -> None:
        """Restore context from persisted state if available."""
        if self.state.context:
            self.set_context(self.state.context)

    def on_stage_change(self, callback: Callable) -> None:
        """Register callback for stage state changes (for TUI integration)."""
        self._on_stage_change = callback
        self.state.on_change(lambda s, st: callback(s, st))

    def _save_state(self) -> None:
        """Persist current state to disk."""
        try:
            self.state.save(self._state_path)
        except Exception as e:
            # Log but don't fail pipeline on state save error
            logging.getLogger(__name__).warning("Failed to save pipeline state: %s", e)

    def _run_stage(self, stage_name: str) -> dict:
        """Execute a single stage through the unified Pipeline executor.

        Builds deterministic kwargs from persisted context and delegates
        to Pipeline.run_stage() — the same path as normal run.
        """
        pipeline = self._get_pipeline()
        kwargs = build_stage_kwargs(stage_name, self._run_context)
        return pipeline.run_stage(stage_name, **kwargs)

    def run_pipeline(
        self,
        input_path: Path,
        output_dir: Path,
        fmt: str = "srt",
        stages: list[str] | None = None,
    ) -> dict:
        """Run full or partial pipeline with policy-based execution.

        Args:
            input_path: Input media file.
            output_dir: Output directory.
            fmt: Export format.
            stages: Specific stages to run (default: all in order).

        Returns:
            Summary dict with timings and results.
        """
        self.workspace.ensure_dirs()
        # Save run context (preserve full context if already set by resume)
        if self._run_context is None:
            self._run_context = PipelineRunContext(
                input_path=str(input_path),
                output_dir=str(output_dir),
                fmt=fmt,
            )
        self._save_state()
        target_stages = stages or self.state.stage_order
        timings: dict[str, float] = {}

        for stage_name in target_stages:
            if self.policy.should_skip(stage_name):
                self.state.mark_skipped(stage_name)
                self.event_log.log_stage_skipped(
                    stage_name, f"policy={self.policy.mode.value}"
                )
                continue

            self._execute_stage_with_retry(stage_name, timings)

        return self._build_summary(timings)

    def retry_stage(self, stage_name: str) -> dict:
        """Retry a failed stage.

        Restores persisted context before execution, resets downstream
        stages using dynamic stage_order (not hardcoded STAGE_ORDER).
        """
        stage = self.state.get(stage_name)
        if not stage.can_retry:
            raise ValueError(
                f"无法重试 {stage.name_cn}："
                f"当前状态={STATUS_CN.get(stage.status, stage.status.value)}，"
                f"已重试 {stage.retry_count}/{stage.max_retries} 次"
            )

        # Restore context before execution
        self._restore_context_from_state()

        # Increment retry count (single source of truth)
        stage.retry_count += 1
        self.state.mark_retrying(stage_name)
        self._save_state()
        self.event_log.log_stage_retry(stage_name, stage.retry_count)
        stage.error_msg = ""

        # Reset all downstream stages to PENDING (dynamic stage_order)
        found = False
        for name in self.state.stage_order:
            if name == stage_name:
                found = True
                continue
            if found:
                self.state.reset(name)
        self._save_state()

        return self._run_stage_with_state_tracking(stage_name)

    def skip_stage(self, stage_name: str) -> None:
        """Skip a stage."""
        self.state.mark_skipped(stage_name)
        self.event_log.log_stage_skipped(stage_name, "manual skip")

    def rollback_stage(self, stage_name: str) -> None:
        """Rollback a stage to PENDING state."""
        self.state.reset(stage_name)
        self.event_log.log(stage_name, "rollback")

    def resume_pipeline(
        self,
        input_path: Path,
        output_dir: Path,
        fmt: str = "srt",
    ) -> dict:
        """Resume pipeline from the first non-success stage.

        Uses persisted stage_order (not hardcoded STAGE_ORDER) so that
        optional stages (script_match, hotword, learn, translate) are
        included in the resume plan when they were part of the original run.
        """
        stage_order = self.state.stage_order

        # Restore context from persisted state if available
        if self.state.context:
            self.set_context(self.state.context)
            # Override args with persisted context values
            input_path = Path(self.state.context.input_path)
            output_dir = Path(self.state.context.output_dir)
            fmt = self.state.context.fmt

        # Find first non-terminal stage (Part I: completed resume = no-op)
        start_idx = None
        for i, name in enumerate(stage_order):
            stage = self.state.get(name)
            if stage.status not in (StageStatus.SUCCESS, StageStatus.SKIPPED):
                start_idx = i
                break

        # All stages completed → no-op
        if start_idx is None:
            return {}

        remaining = stage_order[start_idx:]

        return self.run_pipeline(
            input_path,
            output_dir,
            fmt=fmt,
            stages=remaining,
        )

    def _execute_stage_with_retry(self, stage_name: str, timings: dict) -> None:
        """Execute a stage with automatic retry on failure.

        Uses the unified Pipeline executor for all stage execution.
        Part J: raises after exhausting retries.
        Part K: retry_count incremented only once per attempt.
        """
        self.state.mark_running(stage_name)
        self._save_state()
        self.event_log.log(
            stage_name,
            "start",
            git_commit_hash=self._git_commit_hash,
            workspace_clean=self._workspace_clean,
        )

        start = time.time()
        max_retries = self.state.get(stage_name).max_retries

        for attempt in range(max_retries + 1):
            try:
                result = self._run_stage(stage_name)
                duration = time.time() - start
                timings[stage_name] = duration
                self.state.mark_success(stage_name, result, duration)
                self._save_state()
                self.event_log.log(
                    stage_name,
                    "success",
                    duration=duration,
                    extra={"result_keys": list(result.keys())},
                    git_commit_hash=self._git_commit_hash,
                    workspace_clean=self._workspace_clean,
                )
                return
            except Exception as e:
                stage = self.state.get(stage_name)
                stage.error_msg = str(e)

                if attempt < max_retries:
                    # Part K: only increment retry_count here, not in mark_retrying
                    stage.retry_count = attempt + 1
                    self.state.mark_retrying(stage_name)
                    self._save_state()
                    self.event_log.log(
                        stage_name,
                        "retrying",
                        retry_count=attempt + 1,
                        git_commit_hash=self._git_commit_hash,
                        workspace_clean=self._workspace_clean,
                    )
                else:
                    duration = time.time() - start
                    timings[stage_name] = duration
                    self.state.mark_failed(stage_name, str(e))
                    self._save_state()
                    self.event_log.log(
                        stage_name,
                        "failed",
                        error=str(e),
                        retry_count=attempt + 1,
                        git_commit_hash=self._git_commit_hash,
                        workspace_clean=self._workspace_clean,
                    )
                    # Part J: raise after exhausting retries
                    raise

    def _run_stage_with_state_tracking(self, stage_name: str) -> dict:
        """Run a single stage with state tracking (for retry_stage)."""
        self.workspace.ensure_dirs()
        self.state.mark_running(stage_name)
        self._save_state()
        self.event_log.log_stage_start(stage_name)

        start = time.time()
        try:
            result = self._run_stage(stage_name)
            duration = time.time() - start
            self.state.mark_success(stage_name, result, duration)
            self._save_state()
            self.event_log.log_stage_success(stage_name, duration, result)
            return result
        except Exception as e:
            duration = time.time() - start
            self.state.mark_failed(stage_name, str(e))
            self._save_state()
            self.event_log.log_stage_failed(stage_name, str(e))
            raise

    def _build_summary(self, timings: dict[str, float]) -> dict:
        total = sum(timings.values())
        return {
            "policy": self.policy.to_dict(),
            "timings": {k: round(v, 2) for k, v in timings.items()},
            "total_time_sec": round(total, 2),
            "stages": self.state.summary,
        }
