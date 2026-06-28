"""ASR Draft data contract.

ASRDraft is the output of the ASR stage. It contains raw transcription
results with timestamps that are REFERENCE ONLY — not final timing.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WordTiming(BaseModel):
    """Timing for a single word from ASR."""

    word: str = Field(description="Word text")
    start_sec: float = Field(description="Start time in seconds")
    end_sec: float = Field(description="End time in seconds")
    confidence: Optional[float] = Field(default=None, description="Word confidence")


class ASRDraft(BaseModel):
    """Raw ASR output — REFERENCE timing only, not final subtitle timing.

    Hard rules:
    - ASR does NOT write final.srt
    - ASR timestamps are REFERENCE ONLY, not final timeline
    - This is an intermediate artifact, not a deliverable
    """

    chunk_id: int = Field(description="Source chunk index")
    text: str = Field(description="Transcribed text")
    start_sec: float = Field(description="REFERENCE start time in seconds")
    end_sec: float = Field(description="REFERENCE end time in seconds")
    words: list[WordTiming] = Field(
        default_factory=list, description="Word-level timing if available"
    )
    confidence: Optional[float] = Field(
        default=None, description="Overall confidence score"
    )
    provider: str = Field(default="qwen3_mlx", description="ASR provider identifier")
    model: str = Field(description="Model name used (e.g. asr_0.6b, asr_1.7b)")
    raw_ref: Optional[str] = Field(
        default=None, description="Reference to raw provider output for debugging"
    )

    def is_reference_only(self) -> bool:
        """Confirm this is reference timing, not final."""
        return True  # Always True — ASR never produces final timing
