"""Workspace directory management."""

from __future__ import annotations

from pathlib import Path

from subtap.schemas.config import SubtapConfig


class Workspace:
    """Manages the work/ directory structure for a pipeline run."""

    def __init__(self, config: SubtapConfig, base_dir: Path | None = None):
        self.config = config
        self.root = base_dir or Path(config.workspace.root)
        self.audio_dir = self.root / "audio"
        self.chunks_dir = self.root / "chunks"
        self.asr_dir = self.root / "asr"
        self.cleaned_dir = self.root / "cleaned"
        self.logs_dir = self.root / "logs"

    def ensure_dirs(self) -> None:
        """Create all workspace subdirectories."""
        for d in [
            self.audio_dir,
            self.chunks_dir,
            self.asr_dir,
            self.cleaned_dir,
            self.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def source_audio(self) -> Path:
        return self.audio_dir / "source.wav"

    @property
    def chunks_jsonl(self) -> Path:
        return self.chunks_dir / "chunks.jsonl"

    @property
    def asr_jsonl(self) -> Path:
        return self.asr_dir / "asr.jsonl"

    @property
    def asr_draft_jsonl(self) -> Path:
        return self.asr_dir / "asr_draft.jsonl"

    @property
    def cleaned_jsonl(self) -> Path:
        return self.root / "cleaned.jsonl"

    @property
    def sentences_jsonl(self) -> Path:
        return self.root / "sentences.jsonl"

    @property
    def aligned_jsonl(self) -> Path:
        return self.root / "aligned.jsonl"

    @property
    def script_matched_jsonl(self) -> Path:
        return self.root / "script_matched.jsonl"

    @property
    def aligned_subtitles_jsonl(self) -> Path:
        return self.root / "aligned_subtitles.jsonl"

    @property
    def media_info_path(self) -> Path:
        return self.root / "media_info.json"

    def chunk_path(self, chunk_id: int) -> Path:
        return self.chunks_dir / f"chunk_{chunk_id:04d}.wav"
