"""TUI interface for Subtap pipeline execution."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from subtap.ui.progress import PipelineProgress
from subtap.ui.state import STAGE_CN, reset_state


# ── BaseRunner ──────────────────────────────────────────────────────


class BaseRunner(ABC):
    """Abstract base for all pipeline runners.

    Encapsulates the stage-execution loop, export, and metadata save.
    Subclasses only provide UI callbacks.
    """

    def __init__(self) -> None:
        self.timings: dict[str, float] = {}
        self.total_start: float = 0.0

    # ── stage list ──────────────────────────────────────────────────

    @staticmethod
    def _build_stages(config: Any, translate_to: str | None) -> list[dict]:
        """Build the stage list dynamically from config.

        Returns a list of dicts with keys: key, name, kwargs (or None).
        Optional stages (script_match, translate, learn) are appended
        only when their conditions are met.
        """
        # Resolve glossary_dir from config (CleanConfig.glossary_path)
        clean_cfg = getattr(config, "clean", None)
        glossary_path = getattr(clean_cfg, "glossary_path", None) if clean_cfg else None
        hw_kwargs = {"glossary_dir": glossary_path} if glossary_path else None

        stages: list[dict] = [
            {"key": "prepare", "name": "音频标准化"},
            {"key": "chunk", "name": "音频切段"},
            {"key": "asr", "name": "语音识别"},
            {"key": "clean", "name": "文本清洗", "kwargs": None},
            {"key": "segment", "name": "智能断句"},
            {"key": "align", "name": "时间轴对齐"},
            {"key": "hotword", "name": "热词替换", "kwargs": hw_kwargs},
        ]

        # Optional: script_match
        if getattr(config.output, "script_path", None):
            stages.append({"key": "script_match", "name": "文稿匹配"})

        # learn always runs (discovers hotwords from LLM results)
        # Must run before translate so learned hotwords can be applied
        stages.append({"key": "learn", "name": "热词学习", "kwargs": hw_kwargs})

        # Optional: translate
        if translate_to:
            stages.append({
                "key": "translate",
                "name": "字幕翻译",
                "kwargs": {"target_language": translate_to},
            })

        stages.append({"key": "export", "name": "字幕导出"})
        return stages

    # ── UI hooks (subclass override) ────────────────────────────────

    def _wrap_context(self, runner: Callable[[], Any]) -> Any:
        """Wrap the stage loop in a context manager (e.g. rich.Progress).

        Default: no-op (just call runner() directly).
        """
        return runner()

    @abstractmethod
    def _before_stage(
        self, stage: dict, step_num: int, total_steps: int
    ) -> None:
        """Called before each stage executes."""

    @abstractmethod
    def _after_stage(
        self, stage: dict, result: dict, elapsed: float,
        step_num: int, total_steps: int,
    ) -> None:
        """Called after each stage completes."""

    @abstractmethod
    def _on_complete(self, output_dir: Path, fmt: str, total_time: float) -> None:
        """Called after all stages finish."""

    @abstractmethod
    def _on_error(self, error: Exception) -> None:
        """Called when a stage raises an exception."""

    # ── stage execution loop ────────────────────────────────────────

    def _run_loop(
        self,
        pipeline: Any,
        stages: list[dict],
        enhance: str,
    ) -> None:
        """Execute all stages with timing and callbacks.

        Calls _before_stage / _after_stage around each stage.
        The 'export' stage is skipped here — it is handled by _run_export().
        """
        for i, stage in enumerate(stages):
            # Export is handled separately by _run_export()
            if stage["key"] == "export":
                continue

            step_num = i + 1
            total_steps = len(stages)

            self._before_stage(stage, step_num, total_steps)

            # Build kwargs for this stage
            kwargs = dict(stage.get("kwargs") or {})
            if stage["key"] == "clean":
                kwargs["enhance_mode"] = enhance

            t = time.time()
            result = pipeline.run_stage(stage["key"], **kwargs)
            elapsed = time.time() - t
            self.timings[stage["key"]] = elapsed

            self._after_stage(stage, result, elapsed, step_num, total_steps)

    def _run_pipeline_inner(
        self,
        pipeline: Any,
        input_path: Path,
        output_dir: Path,
        fmt: str,
        enhance: str,
        translate_to: str | None,
        bilingual: str,
    ) -> dict:
        """Core pipeline execution: build stages, run loop, export, save meta."""
        stages = self._build_stages(pipeline.config, translate_to)
        self._run_loop(pipeline, stages, enhance)

        # Export stage (with UI callbacks)
        export_stage = {"key": "export", "name": "字幕导出"}
        export_idx = len(stages) - 1  # export is always last
        self._before_stage(export_stage, export_idx + 1, len(stages))
        t = time.time()
        export_result = self._run_export(pipeline, output_dir, fmt, translate_to, bilingual)
        elapsed = time.time() - t
        self.timings["export"] = elapsed
        self._after_stage(export_stage, export_result, elapsed, export_idx + 1, len(stages))

        total_time = time.time() - self.total_start
        self._on_complete(output_dir, fmt, total_time)
        return self._save_meta(pipeline, input_path, output_dir, fmt, total_time)

    # ── export ──────────────────────────────────────────────────────

    @staticmethod
    def _run_export(
        pipeline: Any,
        output_dir: Path,
        fmt: str,
        translate_to: str | None,
        bilingual: str,
    ) -> dict:
        """Run final exports with consistent parameters from config."""
        from subtap.core.export import run_final_exports

        return run_final_exports(
            pipeline.workspace.aligned_jsonl,
            output_dir,
            punctuation=pipeline.config.output.subtitle_punctuation,
            language=pipeline.config.output.subtitle_language,
            max_chars=pipeline.config.output.max_chars,
            min_chars=pipeline.config.output.min_chars,
            formats={fmt},
            stem=pipeline.config.output.subtitle_stem,
            translate_to=translate_to,
            bilingual=bilingual,
        )

    # ── metadata ────────────────────────────────────────────────────

    def _save_meta(
        self,
        pipeline: Any,
        input_path: Path,
        output_dir: Path,
        fmt: str,
        total_time: float,
    ) -> dict:
        """Save run_meta.json with timings and return the meta dict."""
        meta = {
            "input": str(input_path),
            "work_dir": str(pipeline.workspace.root),
            "output_dir": str(output_dir),
            "format": fmt,
            "alignment_enabled": True,
            "total_time_sec": round(total_time, 2),
            "timings": {k: round(v, 2) for k, v in self.timings.items()},
        }
        (pipeline.workspace.root / "run_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False)
        )
        return meta


# ── RichRunner ──────────────────────────────────────────────────────


class RichRunner(BaseRunner):
    """Rich-based pipeline runner with real-time progress display."""

    def __init__(self) -> None:
        super().__init__()
        self._console: Any = None
        self._progress: Any = None
        self._task_id: Any = None

    def run_pipeline(
        self,
        pipeline: Any,
        input_path: Path,
        output_dir: Path,
        fmt: str = "srt",
        enhance: str = "local",
        translate_to: str | None = None,
        bilingual: str = "off",
    ) -> dict:
        """Execute pipeline with rich progress display."""
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
        )
        from rich.table import Table

        self._console = Console()
        self.total_start = time.time()

        def _run() -> dict:
            return self._run_pipeline_inner(
                pipeline, input_path, output_dir, fmt,
                enhance, translate_to, bilingual,
            )

        # Wrap in rich Progress context
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=self._console,
        ) as progress:
            self._progress = progress
            try:
                meta = _run()
            except Exception as e:
                self._console.print(f"\n[red]✗ 处理失败：{e}[/]")
                raise

        # Summary table
        total_time = meta["total_time_sec"]
        table = Table(title="全流程完成", show_header=True, header_style="bold")
        table.add_column("阶段", style="cyan")
        table.add_column("耗时", justify="right")
        for stage_key, dur in self.timings.items():
            table.add_row(STAGE_CN.get(stage_key, stage_key), f"{dur:.1f}s")
        table.add_row("总耗时", f"[bold]{total_time:.1f}s[/]", style="bold")
        self._console.print(table)
        self._console.print(f"  输出目录：{output_dir}")

        return meta

    def _wrap_context(self, runner: Callable[[], Any]) -> Any:
        return runner()

    def _before_stage(
        self, stage: dict, step_num: int, total_steps: int
    ) -> None:
        self._task_id = self._progress.add_task(stage["name"], total=1)

    def _after_stage(
        self, stage: dict, result: dict, elapsed: float,
        step_num: int, total_steps: int,
    ) -> None:
        self._progress.update(self._task_id, completed=1)
        key = stage["key"]
        if key == "prepare":
            self._console.print(
                f"  [green]✓[/] {result['media_info']['duration']:.1f}s, "
                f"{result['media_info']['sample_rate']}Hz"
            )
        elif key == "chunk":
            self._console.print(f"  [green]✓[/] {result['chunk_count']} 段")
        elif key == "asr":
            self._console.print(f"  [green]✓[/] {result['segment_count']} 条")
        elif key == "clean":
            self._console.print(f"  [green]✓[/] {result['segment_count']} 条")
        elif key == "segment":
            self._console.print(f"  [green]✓[/] {result['sentence_count']} 句")
        elif key == "align":
            self._console.print(f"  [green]✓[/] {result['aligned_count']} 条")
        elif key == "hotword":
            if result.get("replaced", 0) > 0:
                self._console.print(
                    f"  [green]✓[/] 替换 {result['replaced']}/{result['total']} 条"
                )
            else:
                self._console.print("  [dim]·[/] 无热词替换")
        elif key == "script_match":
            if not result.get("skipped"):
                msg = result.get("message", "")
                self._console.print(f"  [green]✓[/] 文稿匹配：{msg}")
                if result.get("warnings"):
                    for w in result["warnings"]:
                        self._console.print(f"    [yellow]⚠[/] {w}")
        elif key == "learn":
            if result.get("learned", 0) > 0:
                self._console.print(
                    f"  [green]✓[/] 学习 {result['learned']} 个热词"
                )
            else:
                self._console.print("  [dim]·[/] 无新热词")
        elif key == "translate":
            self._console.print(
                f"  [green]✓[/] 翻译 {result['translated_count']} 条"
            )
        elif key == "export":
            self._console.print(f"  [green]✓[/] {result['output_path']}")

    def _on_complete(
        self, output_dir: Path, fmt: str, total_time: float
    ) -> None:
        pass  # Summary is printed in run_pipeline after Progress context exits

    def _on_error(self, error: Exception) -> None:
        self._console.print(f"\n[red]✗ 处理失败：{error}[/]")


# ── TUIRunner ───────────────────────────────────────────────────────


class TUIRunner(BaseRunner):
    """TUI-wrapped pipeline execution with Chinese status display."""

    def __init__(
        self, use_tui: bool = True, mode: str = "fast", output_engine: Any = None
    ) -> None:
        super().__init__()
        self.use_tui = use_tui
        self.mode = mode
        self.output_engine = output_engine
        self.progress = PipelineProgress()
        self.state = reset_state()

        if self.use_tui:
            self.state.on_change(self.progress.on_state_change)

    def run_pipeline(
        self,
        pipeline: Any,
        input_path: Path,
        output_dir: Path,
        fmt: str = "srt",
        enhance: str = "local",
        translate_to: str | None = None,
        bilingual: str = "off",
    ) -> dict:
        """Execute full pipeline with TUI feedback."""
        self.total_start = time.time()

        if self.use_tui:
            self.progress.print_header()

        try:
            meta = self._run_pipeline_inner(
                pipeline, input_path, output_dir, fmt,
                enhance, translate_to, bilingual,
            )
        except Exception as e:
            self.state.update(
                status="failed",
                error_msg=str(e),
                suggestion=self._get_suggestion(e),
            )
            if self.use_tui:
                self.progress.print_error(e, self.state)
            raise

        total_time = meta["total_time_sec"]
        if self.use_tui:
            self.progress.print_summary(self.timings, total_time)
            self.progress.print_export_hint(str(output_dir), fmt)

        return meta

    def _before_stage(
        self, stage: dict, step_num: int, total_steps: int
    ) -> None:
        key = stage["key"]
        extra: dict[str, Any] = {}
        if key == "asr":
            extra = {
                "status": "loading_model",
                "model_used": "Qwen3-ASR-0.6B",
                "current_task": f"共 {self.state.total_chunks} 个音频片段",
            }
        elif key == "align":
            extra = {
                "status": "loading_model",
                "model_used": "Qwen3-ForcedAligner-0.6B",
                "current_task": "加载对齐模型",
            }
        self.state.update(stage=key, status="processing", progress=0, **extra)
        if self.use_tui:
            self.progress.print_stage_start(self.state)

    def _after_stage(
        self, stage: dict, result: dict, elapsed: float,
        step_num: int, total_steps: int,
    ) -> None:
        key = stage["key"]
        extra: dict[str, Any] = {}
        if key == "chunk":
            extra["total_chunks"] = result["chunk_count"]
        elif key == "asr":
            extra["segment_count"] = result["segment_count"]
            extra["current_task"] = ""
        elif key == "align":
            extra["current_task"] = ""

        self.state.update(progress=100, status="completed", **extra)

        if self.use_tui:
            if key == "script_match" and result.get("skipped"):
                return  # Don't print skipped script_match
            self.progress.print_stage_result(self.state, result)

    def _on_complete(
        self, output_dir: Path, fmt: str, total_time: float
    ) -> None:
        pass  # Summary is printed in run_pipeline

    def _on_error(self, error: Exception) -> None:
        self.state.update(
            status="failed",
            error_msg=str(error),
            suggestion=self._get_suggestion(error),
        )
        if self.use_tui:
            self.progress.print_error(error, self.state)

    def _save_meta(
        self,
        pipeline: Any,
        input_path: Path,
        output_dir: Path,
        fmt: str,
        total_time: float,
    ) -> dict:
        meta = super()._save_meta(pipeline, input_path, output_dir, fmt, total_time)
        meta["segments"] = self.state.segment_count
        return meta

    def _get_suggestion(self, error: Exception) -> str:
        """Generate Chinese suggestion based on error type."""
        msg = str(error).lower()
        if "model" in msg or "load" in msg:
            return "请检查模型文件是否完整，或运行 subtap models verify"
        if "not found" in msg or "file" in msg:
            return "请检查输入文件路径是否正确"
        if "memory" in msg:
            return "内存不足，请尝试使用更小的模型或减少 batch_size"
        if "mlx" in msg:
            return "MLX 运行时错误，请确认 mlx-audio 已安装且兼容当前系统"
        return "请查看日志文件获取详细信息：work/logs/subtap.log"


# ── PlainRunner ─────────────────────────────────────────────────────


class PlainRunner(BaseRunner):
    """Non-TUI pipeline execution (plain text output)."""

    def __init__(self) -> None:
        super().__init__()
        self._echo: Any = None
        self._completed: int = 0

    def run_pipeline(
        self,
        pipeline: Any,
        input_path: Path,
        output_dir: Path,
        fmt: str = "srt",
        enhance: str = "local",
        translate_to: str | None = None,
        bilingual: str = "off",
    ) -> dict:
        """Execute pipeline with plain text output."""
        import typer

        self._echo = typer.echo
        self._completed = 0
        self.total_start = time.time()

        try:
            meta = self._run_pipeline_inner(
                pipeline, input_path, output_dir, fmt,
                enhance, translate_to, bilingual,
            )
        except Exception as e:
            self._echo(f"\n✗ 处理失败：{e}")
            raise typer.Exit(1)

        total_time = meta["total_time_sec"]
        self._echo("")
        self._echo("═══ 全流程完成 ═══")
        self._echo(f"  总耗时：{total_time:.1f}s")
        for stage, dur in self.timings.items():
            self._echo(f"  {STAGE_CN.get(stage, stage)}：{dur:.1f}s")
        self._echo(f"  输出目录：{output_dir}")

        return meta

    def _before_stage(
        self, stage: dict, step_num: int, total_steps: int
    ) -> None:
        self._completed += 1
        self._echo(f"▸ [{self._completed}/{total_steps}] {stage['name']}...")

    def _after_stage(
        self, stage: dict, result: dict, elapsed: float,
        step_num: int, total_steps: int,
    ) -> None:
        key = stage["key"]
        if key == "prepare":
            self._echo(
                f"  ✓ {result['media_info']['duration']:.1f}s, "
                f"{result['media_info']['sample_rate']}Hz"
            )
        elif key == "chunk":
            self._echo(f"  ✓ {result['chunk_count']} 段")
        elif key == "asr":
            self._echo(f"  ✓ {result['segment_count']} 条")
        elif key == "clean":
            self._echo(f"  ✓ {result['segment_count']} 条")
        elif key == "segment":
            self._echo(f"  ✓ {result['sentence_count']} 句")
        elif key == "align":
            self._echo(f"  ✓ {result['aligned_count']} 条")
        elif key == "hotword":
            if result.get("replaced", 0) > 0:
                self._echo(f"  ✓ 替换 {result['replaced']}/{result['total']} 条")
            else:
                self._echo("  · 无热词替换")
        elif key == "script_match":
            if not result.get("skipped"):
                msg = result.get("message", "")
                self._echo(f"  ✓ {msg}")
                if result.get("warnings"):
                    for w in result["warnings"]:
                        self._echo(f"    ⚠ {w}")
        elif key == "learn":
            if result.get("learned", 0) > 0:
                self._echo(f"  ✓ 学习 {result['learned']} 个热词")
            else:
                self._echo("  · 无新热词")
        elif key == "translate":
            self._echo(f"  ✓ 翻译 {result['translated_count']} 条")
        elif key == "export":
            self._echo(f"  ✓ {result['output_path']}")

    def _on_complete(
        self, output_dir: Path, fmt: str, total_time: float
    ) -> None:
        pass  # Summary is printed in run_pipeline

    def _on_error(self, error: Exception) -> None:
        self._echo(f"\n✗ 处理失败：{error}")
