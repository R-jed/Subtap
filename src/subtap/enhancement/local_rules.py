"""Local rules enhancement: glossary, typo correction, cleanup."""

from __future__ import annotations

import re
import unicodedata

from subtap.enhancement.base import EnhancementMode, EnhancementResult
from subtap.schemas.enhancement import CleanSegment


class LocalRulesEnhancer:
    """Local rules-based enhancement — no LLM, no external API."""

    mode = EnhancementMode.LOCAL

    def enhance(
        self,
        segments: list[CleanSegment],
        glossary: dict[str, str] | None = None,
    ) -> EnhancementResult:
        """Apply local enhancement rules.

        Rules:
        - Unicode normalization (NFKC)
        - Full-width digit conversion
        - Whitespace cleanup
        - Glossary replacement (if provided)

        Args:
            segments: Input segments.
            glossary: Optional glossary for term replacement.

        Returns:
            EnhancementResult with enhanced segments.
        """
        enhanced = []
        changed_count = 0

        for seg in segments:
            original = seg.text
            text = self._normalize_text(original)

            if glossary:
                text = self._apply_glossary(text, glossary)

            changed = text != original
            change_reasons = []
            if changed:
                change_reasons.append("local_cleanup")

            enhanced.append(
                CleanSegment(
                    segment_id=seg.segment_id,
                    source_chunk_id=seg.source_chunk_id,
                    text=text,
                    original_text=seg.original_text,
                    start_sec=seg.start_sec,
                    end_sec=seg.end_sec,
                    enhancement_mode="local",
                    changed=changed or seg.changed,
                    change_reasons=seg.change_reasons + change_reasons,
                )
            )
            if changed:
                changed_count += 1

        return EnhancementResult(
            segments=enhanced,
            mode=EnhancementMode.LOCAL,
            changed_count=changed_count,
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text: NFKC, full-width digits, whitespace."""
        # Unicode normalization
        text = unicodedata.normalize("NFKC", text)
        # Full-width digit conversion (０-９ → 0-9)
        text = re.sub(
            r"[０-９]",
            lambda m: chr(ord(m.group()) - 0xFEE0),
            text,
        )
        # Whitespace cleanup
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _apply_glossary(text: str, glossary: dict[str, str]) -> str:
        """Apply glossary replacements."""
        for wrong, correct in glossary.items():
            text = text.replace(wrong, correct)
        return text
