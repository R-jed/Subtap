"""Final subtitle data contract.

FinalSubtitle is the deliverable output — exported from AlignedSubtitle.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from subtap.schemas.alignment import AlignedSubtitle, AlignedWord


class FinalSubtitle(BaseModel):
    """Final deliverable subtitle — exported ONLY from AlignedSubtitle.

    Hard rules:
    - Can ONLY be created from AlignedSubtitle
    - Contains source_trace for debugging
    - This is the user-facing output
    """

    subtitle_id: int = Field(description="Subtitle index (0-based)")
    start_sec: float = Field(description="Start time in seconds")
    end_sec: float = Field(description="End time in seconds")
    text: str = Field(description="Final subtitle text")
    words: list[AlignedWord] = Field(
        default_factory=list, description="Word-level timing if available"
    )
    alignment_confidence: Optional[float] = Field(
        default=None, description="Alignment confidence from ForcedAligner"
    )
    source_trace: dict = Field(
        default_factory=dict,
        description="Traceability: source chunk, segments, enhancement mode",
    )

    @classmethod
    def from_aligned(cls, aligned: AlignedSubtitle, source_trace: dict | None = None) -> "FinalSubtitle":
        """Create FinalSubtitle from AlignedSubtitle — the ONLY valid creation path.

        Args:
            aligned: AlignedSubtitle from ForcedAligner
            source_trace: Optional traceability info

        Returns:
            FinalSubtitle instance
        """
        return cls(
            subtitle_id=aligned.subtitle_id,
            start_sec=aligned.start_sec,
            end_sec=aligned.end_sec,
            text=aligned.text,
            words=aligned.words,
            alignment_confidence=aligned.alignment_confidence,
            source_trace=source_trace or {},
        )

    def to_srt_block(self, index: int) -> str:
        """Format as SRT block."""
        start = self._format_srt_time(self.start_sec)
        end = self._format_srt_time(self.end_sec)
        return f"{index}\n{start} --> {end}\n{self.text}\n"

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """Format seconds to SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
