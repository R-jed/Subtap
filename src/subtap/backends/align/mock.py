"""Mock aligner for testing."""

from __future__ import annotations

from pathlib import Path

from subtap.schemas.config import AlignConfig
from subtap.schemas.models import SentenceSegment, AlignedSegment


class MockAligner:
    """Deterministic mock aligner — returns original timing unchanged."""

    name = "mock-aligner"

    def __init__(self, config: AlignConfig):
        self.config = config

    def align(
        self,
        sentences: list[SentenceSegment],
        audio_path: Path,
    ) -> list[AlignedSegment]:
        """Pass-through: return original timing."""
        return [
            AlignedSegment(
                sentence_id=s.sentence_id,
                start_sec=s.start_sec,
                end_sec=s.end_sec,
                text=s.text,
            )
            for s in sentences
        ]
