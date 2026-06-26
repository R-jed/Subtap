"""Aligner backend Protocol definition."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from subtap.schemas.models import SentenceSegment, AlignedSegment


@runtime_checkable
class AlignerBackend(Protocol):
    """Protocol for forced alignment backends.

    Receives sentence segments + audio path, returns precise timing.
    """

    name: str

    def align(
        self,
        sentences: list[SentenceSegment],
        audio_path: Path,
    ) -> list[AlignedSegment]:
        """Align sentences to audio waveform for precise timing.

        Args:
            sentences: SentenceSegment list with estimated timing.
            audio_path: Path to source WAV file.

        Returns:
            AlignedSegment list with refined start/end times.
        """
        ...
