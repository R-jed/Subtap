"""Segmentation data contract.

SentenceCandidate is the output of the segmentation stage.
It produces candidate sentences for alignment — NOT final subtitles.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SentenceCandidate(BaseModel):
    """Candidate sentence for alignment — NOT a final subtitle.

    Hard rules:
    - Segmentation only produces candidates, not final subtitle timing
    - cps (characters per second) must be reasonable
    - source_segment_ids traces back to CleanSegments
    """

    sentence_id: int = Field(description="Sentence index (0-based)")
    text: str = Field(description="Sentence text")
    source_segment_ids: list[int] = Field(
        description="Source CleanSegment IDs that contributed to this sentence"
    )
    start_sec: float = Field(description="Estimated start time in seconds")
    end_sec: float = Field(description="Estimated end time in seconds")
    cps: float = Field(
        default=0.0,
        description="Characters per second (text length / duration)",
    )

    @model_validator(mode="after")
    def validate_and_compute_cps(self) -> "SentenceCandidate":
        """Validate timing and compute CPS."""
        if self.start_sec < 0:
            raise ValueError("start_sec must be >= 0")
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be > start_sec")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        # Auto-compute CPS if not set
        if self.cps == 0.0:
            duration = self.end_sec - self.start_sec
            if duration > 0:
                object.__setattr__(
                    self, "cps", len(self.text) / duration
                )
        return self
