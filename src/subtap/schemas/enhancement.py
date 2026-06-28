"""Enhancement data contract.

CleanSegment is the output of the enhancement/clean stage.
LLM can only modify text, NEVER start_sec/end_sec.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class CleanSegment(BaseModel):
    """Enhanced/cleaned segment — LLM can only modify text, NOT timing.

    Hard rules:
    - LLM must NOT modify start_sec / end_sec
    - Empty text is forbidden
    - change_reasons must document what changed
    """

    segment_id: int = Field(description="Segment index (maps to ASR segment)")
    source_chunk_id: int = Field(description="Source chunk index for traceability")
    text: str = Field(description="Enhanced text (LLM output or local rules)")
    original_text: str = Field(description="Original ASR text before enhancement")
    start_sec: float = Field(description="Start time — IMMUTABLE by LLM")
    end_sec: float = Field(description="End time — IMMUTABLE by LLM")
    enhancement_mode: str = Field(
        default="local",
        description="Enhancement mode used: off / local / api",
        pattern="^(off|local|api)$",
    )
    changed: bool = Field(
        default=False, description="Whether text was modified"
    )
    change_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons for changes (e.g. glossary, typo, cleanup)",
    )

    @model_validator(mode="after")
    def validate_timing_immutable(self) -> "CleanSegment":
        """Timing fields must be present and valid."""
        if self.start_sec < 0:
            raise ValueError("start_sec must be >= 0")
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be > start_sec")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        return self

    def text_changed(self) -> bool:
        """Check if text was actually modified."""
        return self.text != self.original_text
