"""Import corrected subtitle files for local learning."""

from __future__ import annotations

from pathlib import Path


def parse_srt_text(content: str) -> list[str]:
    """Parse subtitle text blocks from SRT content."""
    texts: list[str] = []
    for block in content.replace("\r\n", "\n").strip().split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        text_lines = [
            line for line in lines if not line.isdigit() and "-->" not in line
        ]
        if text_lines:
            texts.append(" ".join(text_lines))
    return texts


def import_corrected_srt(path: Path) -> list[str]:
    """Import corrected SRT and return ordered subtitle texts."""
    return parse_srt_text(path.read_text(encoding="utf-8"))
