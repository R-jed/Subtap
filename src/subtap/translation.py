"""Translation helpers for subtitle text."""

from __future__ import annotations


def build_bilingual_text(source_text: str, translated_text: str, order: str) -> str:
    """Build two-line bilingual subtitle text."""
    if order == "source-first":
        return f"{source_text}\n{translated_text}"
    if order == "target-first":
        return f"{translated_text}\n{source_text}"
    raise ValueError(f"未知双语字幕顺序：{order}")
