"""Decision engine: centralized pipeline routing and strategy selection.

This is the SINGLE decision point for all pipeline behavior.
No module should make its own strategy decisions.

Rules:
- All FAST/QUALITY/HYBRID routing decisions here
- All LLM enable/disable decisions here
- All fallback path decisions here
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class PipelineMode(enum.Enum):
    """Pipeline execution modes."""

    FAST = "fast"        # Rule-based only, no LLM, fastest
    QUALITY = "quality"  # Full pipeline with LLM, highest quality
    HYBRID = "hybrid"    # Balance speed and quality


@dataclass
class PipelineDecision:
    """Centralized decision for pipeline execution."""

    mode: PipelineMode
    use_llm: bool
    skip_clean: bool
    skip_align: bool
    use_spacy: bool
    use_fuzzy_match: bool

    @classmethod
    def from_mode(cls, mode: str) -> "PipelineDecision":
        """Create decision from mode string.

        Args:
            mode: One of "fast", "quality", "hybrid".

        Returns:
            PipelineDecision with all routing decisions.
        """
        try:
            pipeline_mode = PipelineMode(mode)
        except ValueError:
            pipeline_mode = PipelineMode.HYBRID

        if pipeline_mode == PipelineMode.FAST:
            return cls(
                mode=pipeline_mode,
                use_llm=False,
                skip_clean=True,
                skip_align=True,
                use_spacy=False,
                use_fuzzy_match=False,
            )
        elif pipeline_mode == PipelineMode.QUALITY:
            return cls(
                mode=pipeline_mode,
                use_llm=True,
                skip_clean=False,
                skip_align=False,
                use_spacy=True,
                use_fuzzy_match=True,
            )
        else:  # HYBRID
            return cls(
                mode=pipeline_mode,
                use_llm=False,
                skip_clean=False,
                skip_align=False,
                use_spacy=True,
                use_fuzzy_match=False,
            )

    def should_run_clean(self) -> bool:
        """Whether to run clean stage."""
        return not self.skip_clean

    def should_run_align(self) -> bool:
        """Whether to run align stage."""
        return not self.skip_align

    def should_use_llm(self) -> bool:
        """Whether to use LLM for enhancement."""
        return self.use_llm

    def should_use_spacy(self) -> bool:
        """Whether to use spaCy for sentence splitting."""
        return self.use_spacy

    def should_use_fuzzy_match(self) -> bool:
        """Whether to use fuzzy matching for glossary."""
        return self.use_fuzzy_match
