"""TUI interface for Subtap pipeline execution."""

from __future__ import annotations

import time
from pathlib import Path

from subtap.ui.state import STAGE_CN


class RichRunner:
    """Rich-based pipeline runner with real-time progress display."""

    def __init__(self):
        self.timings: dict[str, float] = {}
        self.total_start: float = 0.0

    def run_pipeline(
        self,
        pipeline,
        input_path: Path,
        output_dir: Path,
        fmt: str = "srt",
        enhance: str = "local",
        align_enabled: bool = True,
        hotword_enabled: bool = True,
        translate_to: str | None = None,
        bilingual: str = "off",
        hotword_mode: str = "local",
    ) -> dict:
        """Execute pipeline with rich progress display."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
        )
        from rich.table import Table

        console = Console()
        self.total_start = time.time()

        # Build stage list dynamically
        stages = [
            ("prepare", "音频标准化"),
            ("chunk", "音频切段"),
            ("asr", "语音识别"),
            ("clean", "文本清洗"),
            ("segment", "智能断句"),
            ("script_match", "文稿匹配"),
        ]
        if align_enabled:
            stages.append(("align", "时间轴对齐"))
        if translate_to:
            stages.append(("translate", "字幕翻译"))
        stages.append(("export", "字幕导出"))

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            try:
                # Stage 1: prepare
                task = progress.add_task("音频标准化", total=1)
                t = time.time()
                r = pipeline.run_stage("prepare", input_path=input_path)
                self.timings["prepare"] = time.time() - t
                progress.update(task, completed=1)
                console.print(
                    f"  [green]✓[/] {r['media_info']['duration']:.1f}s, "
                    f"{r['media_info']['sample_rate']}Hz"
                )

                # Stage 2: chunk
                task = progress.add_task("音频切段", total=1)
                t = time.time()
                r = pipeline.run_stage("chunk")
                self.timings["chunk"] = time.time() - t
                progress.update(task, completed=1)
                console.print(f"  [green]✓[/] {r['chunk_count']} 段")

                # Stage 3: asr
                task = progress.add_task("语音识别", total=1)
                t = time.time()
                r = pipeline.run_stage("asr")
                self.timings["asr"] = time.time() - t
                progress.update(task, completed=1)
                console.print(f"  [green]✓[/] {r['segment_count']} 条")

                # Stage 4: clean
                task = progress.add_task("文本清洗", total=1)
                t = time.time()
                default_glossary_dir = str(Path.home() / ".subtap" / "glossary")
                r = pipeline.run_stage(
                    "clean",
                    enhance_mode=enhance,
                    hotword_enabled=hotword_enabled,
                    hotword_mode=hotword_mode,
                    hotword_glossary_dir=default_glossary_dir,
                )
                self.timings["clean"] = time.time() - t
                progress.update(task, completed=1)
                console.print(f"  [green]✓[/] {r['segment_count']} 条")

                # Stage 5: segment
                task = progress.add_task("智能断句", total=1)
                t = time.time()
                r = pipeline.run_stage("segment")
                self.timings["segment"] = time.time() - t
                progress.update(task, completed=1)
                console.print(f"  [green]✓[/] {r['sentence_count']} 句")

                # Stage 5.5: script_match (optional)
                t = time.time()
                script_result = pipeline.run_stage("script_match")
                self.timings["script_match"] = time.time() - t
                if not script_result.get("skipped"):
                    msg = script_result.get("message", "")
                    console.print(f"  [green]✓[/] 文稿匹配：{msg}")
                    if script_result.get("warnings"):
                        for w in script_result["warnings"]:
                            console.print(f"    [yellow]⚠[/] {w}")

                # Stage 6: align
                if align_enabled:
                    task = progress.add_task("时间轴对齐", total=1)
                    t = time.time()
                    r = pipeline.run_stage("align")
                    self.timings["align"] = time.time() - t
                    progress.update(task, completed=1)
                    console.print(f"  [green]✓[/] {r['aligned_count']} 条")
                else:
                    self.timings["align"] = 0.0

                self.timings["hotword"] = 0.0

                # Stage 7: translate (optional)
                if translate_to:
                    task = progress.add_task("字幕翻译", total=1)
                    t = time.time()
                    r = pipeline.run_stage(
                        "translate", target_language=translate_to
                    )
                    self.timings["translate"] = time.time() - t
                    progress.update(task, completed=1)
                    console.print(
                        f"  [green]✓[/] 翻译 {r['translated_count']} 条"
                    )
                else:
                    self.timings["translate"] = 0.0

                # Stage 8: export
                task = progress.add_task("字幕导出", total=1)
                t = time.time()
                if align_enabled:
                    from subtap.core.export import run_final_exports

                    r = run_final_exports(
                        pipeline.workspace.aligned_jsonl,
                        output_dir,
                        punctuation=pipeline.config.output.subtitle_punctuation,
                        language=pipeline.config.output.subtitle_language,
                        max_chars=pipeline.config.output.max_chars,
                        min_chars=pipeline.config.output.min_chars,
                        formats=pipeline.config.output.subtitle_formats,
                        stem=pipeline.config.output.subtitle_stem,
                        translate_to=translate_to,
                        bilingual=bilingual,
                    )
                else:
                    from subtap.core.export import run_draft_export

                    r = run_draft_export(pipeline.workspace.asr_jsonl, output_dir)
                self.timings["export"] = time.time() - t
                progress.update(task, completed=1)
                console.print(f"  [green]✓[/] {r['output_path']}")

            except Exception as e:
                console.print(f"\n[red]✗ 处理失败：{e}[/]")
                raise

        total_time = time.time() - self.total_start

        # Summary table
        table = Table(title="全流程完成", show_header=True, header_style="bold")
        table.add_column("阶段", style="cyan")
        table.add_column("耗时", justify="right")
        for stage_key, dur in self.timings.items():
            table.add_row(STAGE_CN.get(stage_key, stage_key), f"{dur:.1f}s")
        table.add_row("总耗时", f"[bold]{total_time:.1f}s[/]", style="bold")
        console.print(table)
        console.print(f"  输出目录：{output_dir}")

        # Save run metadata
        import json

        meta = {
            "input": str(input_path),
            "work_dir": str(pipeline.workspace.root),
            "output_dir": str(output_dir),
            "format": fmt,
            "alignment_enabled": align_enabled,
            "total_time_sec": round(total_time, 2),
            "timings": {k: round(v, 2) for k, v in self.timings.items()},
        }
        (pipeline.workspace.root / "run_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False)
        )
        return meta


class TUIRunner:
    """TUI-wrapped pipeline execution with Chinese status display."""

    def __init__(self, use_tui: bool = True, mode: str = "fast", output_engine=None):
        self.use_tui = use_tui
        self.mode = mode
        self.output_engine = output_engine
        self.progress = PipelineProgress()
        self.state = reset_state()
        self.timings: dict[str, float] = {}
        self.total_start: float = 0.0

        if self.use_tui:
            self.state.on_change(self.progress.on_state_change)

    def run_pipeline(
        self,
        pipeline,
        input_path: Path,
        output_dir: Path,
        fmt: str = "srt",
        enhance: str = "local",
        align_enabled: bool = True,
        hotword_enabled: bool = True,
        translate_to: str | None = None,
        bilingual: str = "off",
        hotword_mode: str = "local",
    ) -> dict:
        """Execute full pipeline with TUI feedback."""
        self.total_start = time.time()

        if self.use_tui:
            self.progress.print_header()

        try:
            # Stage 1: prepare
            self.state.update(stage="prepare", status="processing", progress=0)
            if self.use_tui:
                self.progress.print_stage_start(self.state)

            stage_start = time.time()
            result = pipeline.run_stage("prepare", input_path=input_path)
            self.timings["prepare"] = time.time() - stage_start
            self.state.update(progress=100, status="completed")
            if self.use_tui:
                self.progress.print_stage_result(self.state, result)

            # Stage 2: chunk
            self.state.update(stage="chunk", status="processing", progress=0)
            if self.use_tui:
                self.progress.print_stage_start(self.state)

            stage_start = time.time()
            result = pipeline.run_stage("chunk")
            self.timings["chunk"] = time.time() - stage_start
            total_chunks = result["chunk_count"]
            self.state.update(
                progress=100, status="completed", total_chunks=total_chunks
            )
            if self.use_tui:
                self.progress.print_stage_result(self.state, result)

            # Stage 3: asr
            self.state.update(
                stage="asr",
                status="loading_model",
                progress=0,
                model_used="Qwen3-ASR-0.6B",
                current_task=f"共 {total_chunks} 个音频片段",
            )
            if self.use_tui:
                self.progress.print_stage_start(self.state)

            stage_start = time.time()
            result = pipeline.run_stage("asr")
            self.timings["asr"] = time.time() - stage_start
            self.state.update(
                progress=100,
                status="completed",
                segment_count=result["segment_count"],
                current_task="",
            )
            if self.use_tui:
                self.progress.print_stage_result(self.state, result)

            # Stage 4: clean
            self.state.update(
                stage="clean", status="processing", progress=0, current_task=""
            )
            if self.use_tui:
                self.progress.print_stage_start(self.state)

            stage_start = time.time()
            default_glossary_dir = str(Path.home() / ".subtap" / "glossary")
            result = pipeline.run_stage(
                "clean",
                enhance_mode=enhance,
                hotword_enabled=hotword_enabled,
                hotword_mode=hotword_mode,
                hotword_glossary_dir=default_glossary_dir,
            )
            self.timings["clean"] = time.time() - stage_start
            self.state.update(progress=100, status="completed")
            if self.use_tui:
                self.progress.print_stage_result(self.state, result)

            # Stage 5: segment
            self.state.update(stage="segment", status="processing", progress=0)
            if self.use_tui:
                self.progress.print_stage_start(self.state)

            stage_start = time.time()
            result = pipeline.run_stage("segment")
            self.timings["segment"] = time.time() - stage_start
            self.state.update(progress=100, status="completed")
            if self.use_tui:
                self.progress.print_stage_result(self.state, result)

            # Stage 5.5: script_match (optional)
            stage_start = time.time()
            script_result = pipeline.run_stage("script_match")
            self.timings["script_match"] = time.time() - stage_start
            if not script_result.get("skipped"):
                if self.use_tui:
                    self.progress.print_stage_result(self.state, script_result)

            # Stage 6: align
            if align_enabled:
                self.state.update(
                    stage="align",
                    status="loading_model",
                    progress=0,
                    model_used="Qwen3-ForcedAligner-0.6B",
                    current_task="加载对齐模型",
                )
                if self.use_tui:
                    self.progress.print_stage_start(self.state)

                stage_start = time.time()
                result = pipeline.run_stage("align")
                self.timings["align"] = time.time() - stage_start
                self.state.update(progress=100, status="completed", current_task="")
                if self.use_tui:
                    self.progress.print_stage_result(self.state, result)
            else:
                self.timings["align"] = 0.0

            self.timings["hotword"] = 0.0
            if translate_to:
                self.state.update(stage="translate", status="processing", progress=0)
                stage_start = time.time()
                result = pipeline.run_stage("translate", target_language=translate_to)
                self.timings["translate"] = time.time() - stage_start
                self.state.update(progress=100, status="completed")
                if self.use_tui:
                    self.progress.print_stage_result(self.state, result)
            else:
                self.timings["translate"] = 0.0

            # Stage 8: export
            self.state.update(stage="export", status="processing", progress=0)
            if self.use_tui:
                self.progress.print_stage_start(self.state)

            stage_start = time.time()
            if align_enabled:
                from subtap.core.export import run_final_exports

                result = run_final_exports(
                    pipeline.workspace.aligned_jsonl,
                    output_dir,
                    punctuation=pipeline.config.output.subtitle_punctuation,
                    language=pipeline.config.output.subtitle_language,
                    max_chars=pipeline.config.output.max_chars,
                    min_chars=pipeline.config.output.min_chars,
                    formats=pipeline.config.output.subtitle_formats,
                    stem=pipeline.config.output.subtitle_stem,
                    translate_to=translate_to,
                    bilingual=bilingual,
                )
            else:
                from subtap.core.export import run_draft_export

                result = run_draft_export(pipeline.workspace.asr_jsonl, output_dir)
            self.timings["export"] = time.time() - stage_start
            self.state.update(progress=100, status="completed")
            if self.use_tui:
                self.progress.print_stage_result(self.state, result)

        except Exception as e:
            self.state.update(
                status="failed",
                error_msg=str(e),
                suggestion=self._get_suggestion(e),
            )
            if self.use_tui:
                self.progress.print_error(e, self.state)
            raise

        total_time = time.time() - self.total_start

        if self.use_tui:
            self.progress.print_summary(self.timings, total_time)
            self.progress.print_export_hint(str(output_dir), fmt)

        # Save run metadata
        import json

        meta = {
            "input": str(input_path),
            "work_dir": str(pipeline.workspace.root),
            "output_dir": str(output_dir),
            "format": fmt,
            "alignment_enabled": align_enabled,
            "total_time_sec": round(total_time, 2),
            "timings": {k: round(v, 2) for k, v in self.timings.items()},
            "segments": self.state.segment_count,
        }
        (pipeline.workspace.root / "run_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False)
        )

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


class PlainRunner:
    """Non-TUI pipeline execution (plain text output)."""

    def __init__(self):
        self.timings: dict[str, float] = {}
        self.total_start: float = 0.0

    def run_pipeline(
        self,
        pipeline,
        input_path,
        output_dir,
        fmt="srt",
        enhance: str = "local",
        align_enabled: bool = True,
        hotword_enabled: bool = True,
        translate_to: str | None = None,
        bilingual: str = "off",
        hotword_mode: str = "local",
    ) -> dict:
        """Execute pipeline with plain text output."""
        import typer

        self.total_start = time.time()

        def _echo(msg: str):
            typer.echo(msg)

        try:
            _echo("▸ [1/7] 音频标准化...")
            t = time.time()
            r = pipeline.run_stage("prepare", input_path=input_path)
            self.timings["prepare"] = time.time() - t
            _echo(
                f"  ✓ {r['media_info']['duration']:.1f}s, {r['media_info']['sample_rate']}Hz"
            )

            _echo("▸ [2/7] 音频切段...")
            t = time.time()
            r = pipeline.run_stage("chunk")
            self.timings["chunk"] = time.time() - t
            _echo(f"  ✓ {r['chunk_count']} 段")

            _echo("▸ [3/7] 语音识别...")
            t = time.time()
            r = pipeline.run_stage("asr")
            self.timings["asr"] = time.time() - t
            _echo(f"  ✓ {r['segment_count']} 条")

            _echo("▸ [4/7] 文本清洗...")
            t = time.time()
            default_glossary_dir = str(Path.home() / ".subtap" / "glossary")
            r = pipeline.run_stage(
                "clean",
                enhance_mode=enhance,
                hotword_enabled=hotword_enabled,
                hotword_mode=hotword_mode,
                hotword_glossary_dir=default_glossary_dir,
            )
            self.timings["clean"] = time.time() - t
            _echo(f"  ✓ {r['segment_count']} 条")

            _echo("▸ [5/8] 智能断句...")
            t = time.time()
            r = pipeline.run_stage("segment")
            self.timings["segment"] = time.time() - t
            _echo(f"  ✓ {r['sentence_count']} 句")

            # 文稿匹配（可选）
            t = time.time()
            script_result = pipeline.run_stage("script_match")
            self.timings["script_match"] = time.time() - t
            if not script_result.get("skipped"):
                msg = script_result.get("message", "")
                _echo(f"  ✓ {msg}")
                if script_result.get("warnings"):
                    for w in script_result["warnings"]:
                        _echo(f"    ⚠ {w}")

            if align_enabled:
                _echo("▸ [6/8] 时间轴对齐...")
                t = time.time()
                r = pipeline.run_stage("align")
                self.timings["align"] = time.time() - t
                _echo(f"  ✓ {r['aligned_count']} 条")
            else:
                self.timings["align"] = 0.0
                _echo("▸ [6/8] 时间轴对齐（已关闭）...")
                _echo("  ⚠ 未精对齐，仅生成 draft 粗剪预览")

            self.timings["hotword"] = 0.0
            if translate_to:
                _echo("▸ [7/8] 字幕翻译...")
                t = time.time()
                r = pipeline.run_stage("translate", target_language=translate_to)
                self.timings["translate"] = time.time() - t
                _echo(f"  ✓ 翻译 {r['translated_count']} 条")
            else:
                self.timings["translate"] = 0.0

            _echo(f"▸ [8/8] 字幕导出 ({fmt.upper()})...")
            t = time.time()
            if align_enabled:
                from subtap.core.export import run_final_exports

                r = run_final_exports(
                    pipeline.workspace.aligned_jsonl,
                    output_dir,
                    punctuation=pipeline.config.output.subtitle_punctuation,
                    language=pipeline.config.output.subtitle_language,
                    max_chars=pipeline.config.output.max_chars,
                    min_chars=pipeline.config.output.min_chars,
                    formats=pipeline.config.output.subtitle_formats,
                    stem=pipeline.config.output.subtitle_stem,
                    translate_to=translate_to,
                    bilingual=bilingual,
                )
            else:
                from subtap.core.export import run_draft_export

                r = run_draft_export(pipeline.workspace.asr_jsonl, output_dir)
            self.timings["export"] = time.time() - t
            _echo(f"  ✓ {r['output_path']}")

        except Exception as e:
            _echo(f"\n✗ 处理失败：{e}")
            raise typer.Exit(1)

        total_time = time.time() - self.total_start
        _echo("")
        _echo("═══ 全流程完成 ═══")
        _echo(f"  总耗时：{total_time:.1f}s")
        for stage, dur in self.timings.items():
            _echo(f"  {STAGE_CN.get(stage, stage)}：{dur:.1f}s")
        _echo(f"  输出目录：{output_dir}")

        import json

        meta = {
            "input": str(input_path),
            "work_dir": str(pipeline.workspace.root),
            "output_dir": str(output_dir),
            "format": fmt,
            "alignment_enabled": align_enabled,
            "total_time_sec": round(total_time, 2),
            "timings": {k: round(v, 2) for k, v in self.timings.items()},
        }
        (pipeline.workspace.root / "run_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False)
        )
        return meta
