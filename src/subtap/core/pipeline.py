"""Pipeline orchestrator with stage-based execution."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import MediaInfo
from subtap.core.workspace import Workspace


class Pipeline:
    """Execute Subtap stages with workspace-backed state.

    Each stage reads from and writes to the workspace directory,
    enabling resume from any checkpoint.
    """

    STAGES = ["prepare", "chunk", "asr", "clean", "segment", "align", "export"]

    def __init__(self, config: SubtapConfig, work_dir: Path):
        self.config = config
        self.workspace = Workspace(config, base_dir=work_dir)

    def run_stage(self, stage: str, **kwargs) -> dict:
        """Run a single pipeline stage."""
        handler = {
            "prepare": self._stage_prepare,
            "chunk": self._stage_chunk,
            "asr": self._stage_asr,
            "clean": self._stage_clean,
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
        return {"chunk_count": len(chunks), "chunks_jsonl": str(self.workspace.chunks_jsonl)}

    def _stage_asr(self, backend_name: str | None = None, **_) -> dict:
        from subtap.core.asr import run_asr
        result = run_asr(self.workspace, self.config, backend_name=backend_name)
        return {"segment_count": result["segment_count"], "asr_jsonl": str(self.workspace.asr_jsonl)}

    def _stage_clean(self, llm_backend: str | None = None, glossary_path: str | None = None, **_) -> dict:
        from subtap.core.clean import run_clean
        result = run_clean(
            self.workspace,
            self.config,
            llm_backend_name=llm_backend,
            glossary_path=glossary_path,
        )
        return {"segment_count": result["segment_count"], "cleaned_jsonl": str(self.workspace.cleaned_jsonl)}

    def _stage_segment(self, chunk_start: float = 0.0, chunk_end: float = 1.0, **_) -> dict:
        from subtap.core.segment import run_segment
        result = run_segment(self.workspace, chunk_start, chunk_end)
        return {"sentence_count": result["sentence_count"], "sentences_jsonl": str(self.workspace.sentences_jsonl)}

    def _stage_align(self, backend_name: str | None = None, **_) -> dict:
        from subtap.core.align import run_align
        result = run_align(self.workspace, self.config, backend_name=backend_name)
        return {"aligned_count": result["aligned_count"], "aligned_jsonl": str(self.workspace.aligned_jsonl)}

    def _stage_export(self, fmt: str = "srt", output_dir: str | None = None, stem: str = "output", **_) -> dict:
        from subtap.core.export import run_export
        out = Path(output_dir) if output_dir else self.workspace.root / "output"
        result = run_export(self.workspace.aligned_jsonl, out, fmt=fmt, stem=stem)
        return {"output_path": result["output_path"], "format": result["format"], "segment_count": result["segment_count"]}
