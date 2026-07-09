"""LLM backend Protocol definitions.

Split from the monolithic LLMBackend into focused protocols following
the Interface Segregation Principle. Each protocol represents one
cohesive capability:

- TextCleaner:      segment-level ASR correction
- TextProofreader:  suspicious detection + repair (dict-based I/O)
- HotwordSuggester: glossary-driven hotword replacement (dict-based I/O)
- TextTranslator:   SRT translation

LLMBackend is retained as a Union alias for backward compatibility.
"""

from __future__ import annotations

from typing import Protocol, Union, runtime_checkable

from subtap.schemas.glossary import Glossary
from subtap.schemas.models import RawCleanSegment


@runtime_checkable
class TextCleaner(Protocol):
    """Clean transcription segments using LLM."""

    name: str

    def clean_segments(
        self,
        segments: list[RawCleanSegment],
        glossary: Glossary | None = None,
        style_rules: list[str] | None = None,
    ) -> list[RawCleanSegment]:
        """Clean ASR segments: fix misrecognitions, punctuation, word breaks."""
        ...


@runtime_checkable
class TextProofreader(Protocol):
    """Select and repair suspicious segments (dict-based I/O)."""

    def select_suspicious_segments(self, segments: list[dict]) -> list[int]:
        """Return indices of segments that may contain ASR errors."""
        ...

    def repair_segments(self, segments: list[dict]) -> dict[int, str]:
        """Repair ASR errors → {index: corrected_text}."""
        ...


@runtime_checkable
class HotwordSuggester(Protocol):
    """Suggest hotword replacements (dict-based I/O)."""

    def replace_hotwords(
        self, segments: list[dict], glossary: dict | None
    ) -> dict[int, dict]:
        """Replace domain-specific terms.

        Returns: {index: {"text": corrected, "ops": [{"from": x, "to": y}]}}
        """
        ...


@runtime_checkable
class TextTranslator(Protocol):
    """Translate SRT subtitle text."""

    def translate_srt(
        self,
        srt_text: str,
        target_language: str,
        custom_prompt: str | None = None,
    ) -> str:
        """Translate SRT text to target language.

        Args:
            srt_text: SRT formatted subtitle text.
            target_language: Target language for translation.
            custom_prompt: Optional custom prompt to override default.
        """
        ...


# Backward-compatible alias — combines all four protocols.
# Concrete backends (e.g. OpenAICompatibleLLM) implement all of them.
LLMBackend = Union[TextCleaner, TextProofreader, HotwordSuggester, TextTranslator]
