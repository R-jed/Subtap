"""Tests for script formatting and matching."""

from __future__ import annotations

from subtap.script.match import format_script, match_script_lines


def test_format_script_removes_empty_lines():
    """format_script should keep non-empty script lines in order."""
    assert format_script("第一句\n\n第二句") == ["第一句", "第二句"]


def test_match_script_lines_replaces_text_in_order():
    """match_script_lines should keep timing and replace text in order."""
    segments = [{"start_sec": 0.0, "end_sec": 1.0, "text": "旧文本"}]
    result = match_script_lines(segments, ["新文本"])

    assert result[0]["text"] == "新文本"
    assert result[0]["start_sec"] == 0.0
