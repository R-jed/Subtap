"""Enhancement base: mode enum, result type, and abstract enhancer."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from subtap.schemas.enhancement import CleanSegment


class EnhancementMode(enum.Enum):
    """Enhancement modes."""

    OFF = "off"  # No enhancement
    LOCAL = "local"  # Local rules only (glossary, typo, cleanup)
    API = "api"  # LLM API enhancement


@dataclass
class EnhancementResult:
    """Result of enhancement pass."""

    segments: list[CleanSegment]
    mode: EnhancementMode
    changed_count: int = 0
    api_calls: int = 0
    errors: list[str] = field(default_factory=list)


@runtime_checkable
class Enhancer(Protocol):
    """Protocol for enhancement implementations."""

    mode: EnhancementMode

    def enhance(
        self,
        segments: list[CleanSegment],
        glossary: dict[str, str] | None = None,
    ) -> EnhancementResult:
        """Enhance segment text.

        Rules:
        - Only modify text, NEVER start_sec / end_sec
        - Empty text is forbidden
        - Document all changes in change_reasons

        Args:
            segments: Input segments to enhance.
            glossary: Optional glossary for term replacement.

        Returns:
            EnhancementResult with enhanced segments.
        """
        ...
