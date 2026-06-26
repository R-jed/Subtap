"""PipelineController: state-machine driven pipeline execution with retry, skip, resume."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from subtap.engine.state import PipelineState, StageState, StageStatus, STAGE_ORDER, STAGE_CN
from subtap.engine.policy import ExecutionPolicy
from subtap.engine.events import EventLogger
from subtap.schemas.config import SubtapConfig
from subtap.core.workspace import Workspace


class PipelineController:
    """State-machine driven pipeline execution.

    Supports: run, retry, skip, resume, rollback.
    All state transitions are tracked and logged.
    """

    def __init__(self, config: SubtapConfig, work_dir: Path, policy: str = "local"):
        self.config = config
        self.workspace = Workspace(config, base_dir=work_dir)
        self.policy = ExecutionPolicy(policy)
        self.state = PipelineState()
        self.event_log = EventLogger(self.workspace.logs_dir)
        self._stage_handlers: dict[str, Callable] = {
            "prepare": self._run_prepare,
            "chunk": self._run_chunk,
            "asr": self._run_asr,
            "clean": self._run_clean,
            "segment": self._run_segment,
            "align": self._run_align,
            "export": self._run_export,
        }
        self._on_stage_change: Optional[Callable] = None
        # Pre-flight state (set by CLI before run)
        self._git_commit_hash: str = ""
        self._workspace_clean: bool = True

    def set_preflight_state(self, git_commit_hash: str = "", workspace_clean: bool = True) -> None:
        """Set pre-flight state for event logging."""
        self._git_commit_hash = git_commit_hash
        self._workspace_clean = workspace_clean

    def on_stage_change(self, callback: Callable) -> None:
        """Register callback for stage state changes (for TUI integration)."""
        self._on_stage_change = callback
        self.state.on_change(lambda s, st: callback(s, st))

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
        target_stages = stages or STAGE_ORDER
        timings: dict[str, float] = {}

        for stage_name in target_stages:
            if self.policy.should_skip(stage_name):
                self.state.mark_skipped(stage_name)
                self.event_log.log_stage_skipped(stage_name, f"policy={self.policy.mode.value}")
                continue

            self._execute_stage_with_retry(stage_name, timings)

        return self._build_summary(timings)

    def run_stage(self, stage_name: str, **kwargs) -> dict:
        """Run a single stage with state tracking."""
        self.workspace.ensure_dirs()
        self.state.mark_running(stage_name)
        self.event_log.log_stage_start(stage_name)

        start = time.time()
        try:
            handler = self._stage_handlers.get(stage_name)
            if handler is None:
                raise ValueError(f"Unknown stage: {stage_name}")
            result = handler(**kwargs)
            duration = time.time() - start
            self.state.mark_success(stage_name, result, duration)
            self.event_log.log_stage_success(stage_name, duration, result)
            return result
        except Exception as e:
            duration = time.time() - start
            self.state.mark_failed(stage_name, str(e))
            self.event_log.log_stage_failed(stage_name, str(e))
            raise

    def retry_stage(self, stage_name: str) -> dict:
        """Retry a failed stage."""
        stage = self.state.get(stage_name)
        if not stage.can_retry:
            raise ValueError(
                f"无法重试 {stage.name_cn}："
                f"当前状态={STATUS_CN.get(stage.status, stage.status.value)}，"
                f"已重试 {stage.retry_count}/{stage.max_retries} 次"
            )

        self.state.mark_retrying(stage_name)
        self.event_log.log_stage_retry(stage_name, stage.retry_count)
        stage.error_msg = ""

        return self.run_stage(stage_name)

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
        """Resume pipeline from the first non-success stage."""
        start_idx = 0
        for i, name in enumerate(STAGE_ORDER):
            stage = self.state.get(name)
            if stage.status not in (StageStatus.SUCCESS, StageStatus.SKIPPED):
                start_idx = i
                break

        remaining = STAGE_ORDER[start_idx:]
        if not remaining:
            typer.echo("所有阶段已完成，无需恢复")
            return {}

        from subtap.ui.tui import PlainRunner
        runner = PlainRunner()
        return runner.run_pipeline(
            type(self)(self.config, self.workspace.root, self.policy.mode.value),
            input_path, output_dir, fmt=fmt,
            skip_clean=self.policy.should_skip("clean"),
            skip_align=self.policy.should_skip("align"),
        )

    def _execute_stage_with_retry(self, stage_name: str, timings: dict) -> None:
        """Execute a stage with automatic retry on failure."""
        self.state.mark_running(stage_name)
        self.event_log.log(
            stage_name, "start",
            git_commit_hash=self._git_commit_hash,
            workspace_clean=self._workspace_clean,
        )

        start = time.time()
        max_retries = self.state.get(stage_name).max_retries

        for attempt in range(max_retries + 1):
            try:
                handler = self._stage_handlers.get(stage_name)
                if handler is None:
                    raise ValueError(f"Unknown stage: {stage_name}")
                result = handler()
                duration = time.time() - start
                timings[stage_name] = duration
                self.state.mark_success(stage_name, result, duration)
                self.event_log.log(
                    stage_name, "success", duration=duration,
                    extra={"result_keys": list(result.keys())},
                    git_commit_hash=self._git_commit_hash,
                    workspace_clean=self._workspace_clean,
                )
                return
            except Exception as e:
                stage = self.state.get(stage_name)
                stage.error_msg = str(e)

                if attempt < max_retries:
                    stage.retry_count = attempt + 1
                    self.state.mark_retrying(stage_name)
                    self.event_log.log(
                        stage_name, "retrying", retry_count=attempt + 1,
                        git_commit_hash=self._git_commit_hash,
                        workspace_clean=self._workspace_clean,
                    )
                else:
                    duration = time.time() - start
                    timings[stage_name] = duration
                    self.state.mark_failed(stage_name, str(e))
                    self.event_log.log(
                        stage_name, "failed", error=str(e), retry_count=attempt + 1,
                        git_commit_hash=self._git_commit_hash,
                        workspace_clean=self._workspace_clean,
                    )

    def _build_summary(self, timings: dict[str, float]) -> dict:
        total = sum(timings.values())
        return {
            "policy": self.policy.to_dict(),
            "timings": {k: round(v, 2) for k, v in timings.items()},
            "total_time_sec": round(total, 2),
            "stages": self.state.summary,
        }

    # ── Stage handlers (delegate to existing pipeline modules) ──

    def _run_prepare(self, **_) -> dict:
        from subtap.core.media import prepare_media
        media_info = prepare_media(
            Path(self.workspace.root / ".input_path"),
            self.workspace, self.config,
        )
        return {"media_info": media_info.model_dump()}

    def _run_chunk(self, **_) -> dict:
        from subtap.core.vad import split_chunks
        chunks = split_chunks(self.workspace, self.config)
        return {"chunk_count": len(chunks), "chunks_jsonl": str(self.workspace.chunks_jsonl)}

    def _run_asr(self, **_) -> dict:
        from subtap.core.asr import run_asr
        result = run_asr(self.workspace, self.config, backend_name=self.policy.asr_backend)
        return {"segment_count": result["segment_count"], "asr_jsonl": str(self.workspace.asr_jsonl)}

    def _run_clean(self, **_) -> dict:
        from subtap.core.clean import run_clean
        result = run_clean(self.workspace, self.config)
        return {"segment_count": result["segment_count"], "cleaned_jsonl": str(self.workspace.cleaned_jsonl)}

    def _run_segment(self, **_) -> dict:
        from subtap.core.segment import run_segment
        result = run_segment(self.workspace, self.config)
        return {"sentence_count": result["sentence_count"], "sentences_jsonl": str(self.workspace.sentences_jsonl)}

    def _run_align(self, **_) -> dict:
        from subtap.core.align import run_align
        result = run_align(self.workspace, self.config, backend_name=self.policy.align_backend)
        return {"aligned_count": result["aligned_count"], "aligned_jsonl": str(self.workspace.aligned_jsonl)}

    def _run_export(self, fmt: str = "srt", output_dir: str | None = None, **_) -> dict:
        from subtap.core.export import run_export
        out = Path(output_dir) if output_dir else self.workspace.root / "output"
        result = run_export(self.workspace.aligned_jsonl, out, fmt=fmt)
        return {"output_path": result["output_path"], "format": result["format"], "segment_count": result["segment_count"]}


# Avoid circular import at module level
import typer  # noqa: E402
from subtap.engine.state import STATUS_CN  # noqa: E402
