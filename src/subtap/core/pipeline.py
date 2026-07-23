"""Pipeline orchestrator with stage-based execution."""

from __future__ import annotations

import json
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
        "script_match",
        "align",
        "hotword",
        "translate",
        "learn",
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
            "segment": self._stage_segment,
            "script_match": self._stage_script_match,
            "align": self._stage_align,
            "hotword": self._stage_hotword,
            "learn": self._stage_learn,
            "translate": self._stage_translate,
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
                item_index=index,
                total_items=total,
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
        **_,
    ) -> dict:
        from subtap.core.clean import run_clean

        result = run_clean(
            self.workspace,
            self.config,
            llm_backend_name=llm_backend,
            glossary_path=glossary_path,
            style_rules=self.config.clean.style_rules or None,
            enhance_mode=enhance_mode,
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
            glossary_path=kwargs.get("glossary_path"),
            mode=kwargs.get("mode", "local"),
            lang=kwargs.get("lang", "zh"),
        )

    def _stage_segment(
        self, chunk_start: float | None = None, chunk_end: float | None = None, **_
    ) -> dict:
        from subtap.core.segment import run_segment

        result = run_segment(
            self.workspace,
            chunk_start,
            chunk_end,
            language=self.config.output.subtitle_language,
        )
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

    def _stage_script_match(self, **_) -> dict:
        """文稿匹配阶段（可选）。

        使用 rapidfuzz 相似度匹配，基于参考文稿校正 ASR 输出。
        当 script_path 配置时自动启用。
        """
        if not self.config.output.script_path:
            return {"skipped": True}
        from subtap.script.match import match_from_file

        script_path = Path(self.config.output.script_path)
        if not script_path.exists():
            raise ValueError(f"文稿文件不存在：{script_path}")

        if not self.workspace.sentences_jsonl.exists():
            raise ValueError("sentences.jsonl 不存在，请先执行 segment 阶段")

        # 读取 sentences.jsonl
        segments = []
        with open(self.workspace.sentences_jsonl) as f:
            for line in f:
                if line.strip():
                    segments.append(json.loads(line))

        result, report = match_from_file(
            segments, script_path, mode=self.config.output.script_mode
        )

        # 写入 script_matched.jsonl
        with open(self.workspace.script_matched_jsonl, "w") as f:
            for seg in result:
                f.write(json.dumps(seg, ensure_ascii=False) + "\n")

        return {
            "matched": report.matched,
            "corrected": report.corrected,
            "skipped": report.skipped,
            "warnings": report.warnings,
            "message": report.message,
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

    def _stage_learn(
        self,
        glossary_path: str | Path | None = None,
        **_,
    ) -> dict:
        """Learn hotwords from LLM ops recorded during clean stage."""
        import json

        from subtap.ai.glossary_learner import GlossaryLearner, save_learned_hotwords

        if glossary_path is not None and not Path(glossary_path).is_file():
            raise FileNotFoundError(f"术语表不存在：{glossary_path}")

        ops_path = self.workspace.root / "llm_hotword_ops.jsonl"
        if not ops_path.exists():
            return {"learned": 0}

        ops = []
        for line in ops_path.read_text(encoding="utf-8").strip().splitlines():
            if line.strip():
                ops.append(json.loads(line))

        if not ops:
            return {"learned": 0}

        learner = GlossaryLearner()
        update = learner.learn_from_ops(ops)

        if not update.new_terms:
            ops_path.unlink(missing_ok=True)
            return {"learned": 0}

        from subtap.core.user_resources import ensure_learned_glossary

        hotwords_path = ensure_learned_glossary()
        save_learned_hotwords(update, hotwords_path)

        # Clean up ops file after learning
        ops_path.unlink(missing_ok=True)

        return {"learned": len(update.new_terms), "path": str(hotwords_path)}

    def _stage_translate(
        self,
        target_language: str | None = None,
        llm_backend: str | None = None,
        **_,
    ) -> dict:
        if not target_language:
            raise ValueError("target_language required for translate stage")
        from subtap.core.translate import run_translate

        return run_translate(
            self.workspace,
            self.config,
            target_language=target_language,
            llm_backend_name=llm_backend,
        )

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
