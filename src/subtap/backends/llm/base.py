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
        """Clean transcription segments using LLM."""
        ...

    def select_suspicious_segments(self, segments: list[dict]) -> list[int]:
        """Select segments that may contain ASR errors."""
        ...

    def repair_segments(self, segments: list[dict]) -> dict[int, str]:
        """Repair ASR errors in selected segments."""
        ...

    def replace_hotwords(
        self, segments: list[dict], glossary: dict | None
    ) -> dict[int, dict]:
        """Replace domain-specific terms using glossary.

        Returns: {index: {"text": corrected, "ops": [{"from": x, "to": y}]}}
        """
        ...

    def translate_srt(self, srt_text: str, target_language: str) -> str:
        """Translate SRT text to target language."""
        ...
