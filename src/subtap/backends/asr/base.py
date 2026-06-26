"""ASR backend Protocol definition."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from subtap.schemas.models import Chunk, ASRSegment


@runtime_checkable
class ASRBackend(Protocol):
    """Protocol for ASR backends.

    Each backend receives a list of audio chunks and returns
    transcription segments. Backends are responsible only for
    transcription — not alignment, not VAD, not LLM processing.
    """

    name: str

    def transcribe(
        self,
        chunks: list[Chunk],
        language: str | None = None,
        hotwords: list[str] | None = None,
    ) -> list[ASRSegment]:
        """Transcribe audio chunks into text segments.

        Args:
            chunks: List of Chunk models with paths to WAV files.
            language: Optional language hint.
            hotwords: Optional domain-specific vocabulary.

        Returns:
            List of ASRSegment models, one per transcription segment.
        """
        ...
