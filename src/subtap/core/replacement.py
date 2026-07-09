"""Deterministic text replacement (before LLM stage).

Only performs string replacements — no semantic changes.
"""

from __future__ import annotations

import re
from typing import Optional

from subtap.schemas.glossary import Glossary
from subtap.schemas.models import ASRSegment, RawCleanSegment


def apply_replacements(
    segments: list[ASRSegment],
    glossary: Optional[Glossary] = None,
) -> list[RawCleanSegment]:
    """Apply deterministic replacements to ASR segments.

    Runs glossary replacements in order. No LLM, no semantic changes.
    Returns RawCleanSegment list with glossary_applied tracking.
    """
    if glossary is None:
        glossary = Glossary()

    replacements = glossary.get_replacements()
    results: list[RawCleanSegment] = []

    for seg in segments:
        text = seg.text
        applied: list[str] = []

        for find_str, replace_str in replacements:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(find_str), re.IGNORECASE)
            if pattern.search(text):
                text = pattern.sub(replace_str, text)
                applied.append(f"{find_str}→{replace_str}")

        results.append(
            RawCleanSegment(
                segment_id=seg.segment_id,
                source_chunk_id=seg.chunk_id,
                original_text=seg.text,
                cleaned_text=text,
                glossary_applied=applied,
            )
        )

    return results
