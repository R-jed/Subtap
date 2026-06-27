"""Script formatting and simple sequential matching."""

from __future__ import annotations


def format_script(text: str) -> list[str]:
    """Return non-empty script lines in order."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def match_script_lines(segments: list[dict], lines: list[str]) -> list[dict]:
    """Replace segment text with script lines by order while preserving timing."""
    result = []
    for index, segment in enumerate(segments):
        item = dict(segment)
        if index < len(lines):
            item["text"] = lines[index]
        result.append(item)
    return result
