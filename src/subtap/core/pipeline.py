"""Pipeline orchestrator with stage-based execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from subtap.schemas.config import SubtapConfig
from subtap.core.workspace import Workspace
from subtap.metrics.events import EventBus, EventType, make_pipeline_event


class Pipeline:
    """Execute Subtap stages with workspace-backed state.

    Each stage reads from and writes to the workspace directory,
    enabling resume from any checkpoint.
    """

    STAGES = [
        "prepare",
        "chunk",
        "asr",
        "clean",
        "segment",
        "align",
        "hotword",
        "export",
    ]

    def __init__(
        self,
        config: SubtapConfig,
        work_dir: Path,
        event_bus: EventBus | None = None,
        task_id: str = "local",
    ):
        self.config = config
        self.workspace = Workspace(config, base_dir=work_dir)
        self.event_bus = event_bus
        self.task_id = task_id

    def _publish_event(self, event_type: EventType, *, stage: str, **data: Any) -> None:
        """Publish a non-blocking pipeline event without UI coupling."""
        if self.event_bus is None:
            return
        self.event_bus.publish_nowait(
            make_pipeline_event(
                event_type,
                task_id=self.task_id,
                stage=stage,
                **data,
            )
        )

    def run_stage(self, stage: str, **kwargs) -> dict:
        """Run a single pipeline stage."""
        handler = {
            "prepare": self._stage_prepare,
            "chunk": self._stage_chunk,
            "asr": self._stage_asr,
            "clean": self._stage_clean,
            "hotword": self._stage_hotword,
            "segment": self._stage_segment,
            "align": self._stage_align,
            "export": self._stage_export,
        }.get(stage)

        if handler is None:
            raise ValueError(f"Unknown stage: {stage}")

        return handler(**kwargs)

    def _stage_prepare(self, input_path: Optional[Path] = None, **_) -> dict:
        from subtap.core.media import prepare_media

        if input_path is None:
            raise ValueError("input_path required for prepare stage")
        media_info = prepare_media(input_path, self.workspace, self.config)
        return {"media_info": media_info.model_dump()}

    def _stage_chunk(self, **_) -> dict:
        from subtap.core.vad import split_chunks

        chunks = split_chunks(self.workspace, self.config)
        total = len(chunks) or 1
        for index, chunk in enumerate(chunks, start=1):
            self._publish_event(
                EventType.AUDIO_CHUNK_READY,
                stage="chunk",
                chunk_id=chunk.chunk_id,
                progress=round(index / total * 100),
                duration_sec=chunk.end_sec - chunk.start_sec,
                message_zh="音频片段已准备",
            )
        return {
            "chunk_count": len(chunks),
            "chunks_jsonl": str(self.workspace.chunks_jsonl),
        }

    def _stage_asr(self, backend_name: str | None = None, **_) -> dict:
        from subtap.core.asr import run_asr

        result = run_asr(
            self.workspace,
            self.config,
            backend_name=backend_name,
            event_bus=self.event_bus,
            task_id=self.task_id,
        )
        return {
            "segment_count": result["segment_count"],
            "asr_jsonl": str(self.workspace.asr_jsonl),
        }

    def _stage_clean(
        self,
        llm_backend: str | None = None,
        glossary_path: str | None = None,
        enhance_mode: str | None = None,
        hotword_enabled: bool = True,
        hotword_mode: str = "local",
        hotword_lang: str = "zh",
        hotword_glossary_dir: str | None = None,
        **_,
    ) -> dict:
        from subtap.core.clean import run_clean

        result = run_clean(
            self.workspace,
            self.config,
            llm_backend_name=llm_backend,
            glossary_path=glossary_path,
            enhance_mode=enhance_mode,
            hotword_enabled=hotword_enabled,
            hotword_mode=hotword_mode,
            hotword_lang=hotword_lang,
            hotword_glossary_dir=hotword_glossary_dir,
        )
        self._publish_event(
            EventType.ENHANCEMENT_READY,
            stage="clean",
            progress=100,
            message_zh="字幕文本增强完成",
        )
        return {
            "segment_count": result["segment_count"],
            "cleaned_jsonl": str(self.workspace.cleaned_jsonl),
        }

    def _stage_hotword(self, **kwargs) -> dict:
        from subtap.core.hotword import run_hotword

        return run_hotword(
            self.workspace,
            glossary_dir=kwargs.get("glossary_dir"),
            mode=kwargs.get("mode", "local"),
            lang=kwargs.get("lang", "zh"),
        )

    def _stage_segment(
        self, chunk_start: float = 0.0, chunk_end: float = 1.0, **_
    ) -> dict:
        from subtap.core.segment import run_segment

        result = run_segment(self.workspace, chunk_start, chunk_end)
        self._publish_event(
            EventType.SENTENCE_CANDIDATE_READY,
            stage="segment",
            progress=100,
            message_zh="字幕候选句已生成",
        )
        return {
            "sentence_count": result["sentence_count"],
            "sentences_jsonl": str(self.workspace.sentences_jsonl),
        }

    def _stage_align(self, backend_name: str | None = None, **_) -> dict:
        from subtap.core.align import run_align

        result = run_align(
            self.workspace,
            self.config,
            backend_name=backend_name,
            event_bus=self.event_bus,
            task_id=self.task_id,
        )
        return {
            "aligned_count": result["aligned_count"],
            "aligned_jsonl": str(self.workspace.aligned_jsonl),
        }

    def _stage_export(
        self, fmt: str = "srt", output_dir: str | None = None, stem: str = "output", **_
    ) -> dict:
        from subtap.core.export import run_export

        out = Path(output_dir) if output_dir else self.workspace.root / "output"
        result = run_export(
            self.workspace.aligned_jsonl,
            out,
            fmt=fmt,
            stem=stem,
            max_chars=self.config.output.max_chars,
            min_chars=self.config.output.min_chars,
            punctuation=self.config.output.subtitle_punctuation,
            language=self.config.output.subtitle_language,
        )
        return {
            "output_path": result["output_path"],
            "format": result["format"],
            "segment_count": result["segment_count"],
        }

    def cleanup(self) -> dict[str, Any]:
        """清理 L1 临时文件。"""
        if not self.config.cleanup.auto_cleanup:
            return {"cleaned_count": 0, "cleaned_files": [], "is_clean": True}

        from subtap.engine.cleanroom import Cleanroom

        cleanroom = Cleanroom(self.workspace.root)
        return cleanroom.clean_temp_files(
            exclude_chunks=self.config.cleanup.keep_chunks
        )
