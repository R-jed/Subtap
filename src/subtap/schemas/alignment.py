"""Alignment data contract.

AlignedSubtitle is the output of the ForcedAligner stage.
This is the FINAL timing source — only AlignedSubtitle can be exported.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class AlignedWord(BaseModel):
    """Word-level timing from forced alignment."""

    word: str = Field(description="Word text")
    start_sec: float = Field(description="Aligned start time in seconds")
    end_sec: float = Field(description="Aligned end time in seconds")
    confidence: Optional[float] = Field(
        default=None, description="Alignment confidence"
    )


class AlignedSubtitle(BaseModel):
    """Aligned subtitle with FINAL timing from ForcedAligner.

    Hard rules:
    - ForcedAligner is the ONLY source of final timing
    - Export can ONLY happen from AlignedSubtitle
    - LLM cannot modify these timestamps
    """

    subtitle_id: int = Field(description="Subtitle index (0-based)")
    start_sec: float = Field(description="FINAL aligned start time in seconds")
    end_sec: float = Field(description="FINAL aligned end time in seconds")
    text: str = Field(description="Subtitle text")
    words: list[AlignedWord] = Field(
        default_factory=list,
        description="Word-level timing from alignment",
    )
    alignment_confidence: Optional[float] = Field(
        default=None, description="Overall alignment confidence"
    )

    @model_validator(mode="after")
    def validate_timing(self) -> "AlignedSubtitle":
        """Validate timing is sane."""
        if self.start_sec < 0:
            raise ValueError("start_sec must be >= 0")
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be > start_sec")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        return self

    def duration_sec(self) -> float:
        """Duration in seconds."""
        return self.end_sec - self.start_sec

    def cps(self) -> float:
        """Characters per second."""
        duration = self.duration_sec()
        return len(self.text) / duration if duration > 0 else 0.0
