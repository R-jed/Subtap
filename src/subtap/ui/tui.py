"""TUI interface for Subtap pipeline execution."""

from __future__ import annotations

import time
from pathlib import Path

from subtap.ui.state import STAGE_CN, reset_state
from subtap.ui.progress import PipelineProgress


class TUIRunner:
    """TUI-wrapped pipeline execution with Chinese status display."""

    def __init__(self, use_tui: bool = True, mode: str = "hybrid", output_engine=None):
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
        skip_clean: bool = False,
        skip_align: bool = False,
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

            # Stage 4: clean (optional)
            if not skip_clean:
                self.state.update(
                    stage="clean", status="processing", progress=0, current_task=""
                )
                if self.use_tui:
                    self.progress.print_stage_start(self.state)

                stage_start = time.time()
                result = pipeline.run_stage("clean")
                self.timings["clean"] = time.time() - stage_start
                self.state.update(progress=100, status="completed")
                if self.use_tui:
                    self.progress.print_stage_result(self.state, result)
            else:
                if self.use_tui:
                    self.progress.print_skip("文本清洗", "--skip-clean")
                # Convert ASR → CleanSegment format
                from subtap.core.clean import load_asr_segments, write_clean_segments
                from subtap.schemas.models import CleanSegment

                asr_segs = load_asr_segments(pipeline.workspace.asr_jsonl)
                write_clean_segments(
                    [
                        CleanSegment(
                            segment_id=s.segment_id,
                            original_text=s.text,
                            cleaned_text=s.text,
                            glossary_applied=[],
                        )
                        for s in asr_segs
                    ],
                    pipeline.workspace.cleaned_jsonl,
                )

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

            # Stage 6: align (optional)
            if not skip_align:
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
                if self.use_tui:
                    self.progress.print_skip("时间轴对齐", "--skip-align")
                import shutil

                shutil.copy2(
                    pipeline.workspace.sentences_jsonl, pipeline.workspace.aligned_jsonl
                )

            # Stage 7: export
            self.state.update(stage="export", status="processing", progress=0)
            if self.use_tui:
                self.progress.print_stage_start(self.state)

            stage_start = time.time()
            from subtap.core.export import run_export

            result = run_export(pipeline.workspace.aligned_jsonl, output_dir, fmt=fmt)
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
        skip_clean=False,
        skip_align=False,
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

            if not skip_clean:
                _echo("▸ [4/7] 文本清洗...")
                t = time.time()
                r = pipeline.run_stage("clean")
                self.timings["clean"] = time.time() - t
                _echo(f"  ✓ {r['segment_count']} 条")
            else:
                _echo("▸ [4/7] 跳过文本清洗 (--skip-clean)")
                from subtap.core.clean import load_asr_segments, write_clean_segments
                from subtap.schemas.models import CleanSegment

                asr_segs = load_asr_segments(pipeline.workspace.asr_jsonl)
                write_clean_segments(
                    [
                        CleanSegment(
                            segment_id=s.segment_id,
                            original_text=s.text,
                            cleaned_text=s.text,
                            glossary_applied=[],
                        )
                        for s in asr_segs
                    ],
                    pipeline.workspace.cleaned_jsonl,
                )

            _echo("▸ [5/7] 智能断句...")
            t = time.time()
            r = pipeline.run_stage("segment")
            self.timings["segment"] = time.time() - t
            _echo(f"  ✓ {r['sentence_count']} 句")

            if not skip_align:
                _echo("▸ [6/7] 时间轴对齐...")
                t = time.time()
                r = pipeline.run_stage("align")
                self.timings["align"] = time.time() - t
                _echo(f"  ✓ {r['aligned_count']} 条")
            else:
                _echo("▸ [6/7] 跳过时间轴对齐 (--skip-align)")
                import shutil

                shutil.copy2(
                    pipeline.workspace.sentences_jsonl, pipeline.workspace.aligned_jsonl
                )

            _echo(f"▸ [7/7] 字幕导出 ({fmt.upper()})...")
            t = time.time()
            from subtap.core.export import run_export

            r = run_export(pipeline.workspace.aligned_jsonl, output_dir, fmt=fmt)
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
            "total_time_sec": round(total_time, 2),
            "timings": {k: round(v, 2) for k, v in self.timings.items()},
        }
        (pipeline.workspace.root / "run_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False)
        )
        return meta
