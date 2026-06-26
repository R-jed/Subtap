"""LLM backend Protocol definition."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from subtap.schemas.glossary import Glossary
from subtap.schemas.models import CleanSegment


@runtime_checkable
class LLMBackend(Protocol):
    """Protocol for LLM cleaning backends.

    Each backend receives pre-replaced segments and applies
    LLM-based cleaning (ASR error correction, punctuation, segmentation).
    """

    name: str

    def clean_segments(
        self,
        segments: list[CleanSegment],
        glossary: Glossary | None = None,
        style_rules: list[str] | None = None,
    ) -> list[CleanSegment]:
        """Clean transcription segments using LLM.

        Rules:
        - Do NOT change semantics
        - Do NOT summarize
        - Do NOT delete content
        - Only fix ASR errors, add punctuation, improve segmentation

        Args:
            segments: Pre-replaced CleanSegments.
            glossary: Glossary for term awareness.
            style_rules: Additional style instructions.

        Returns:
            Updated CleanSegments with cleaned_text.
        """
        ...
