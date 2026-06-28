"""Tests for script formatting and matching."""

from __future__ import annotations

from typer.testing import CliRunner

from subtap.cli import app
from subtap.script.match import format_script, match_script_lines
from subtap.schemas.models import AlignedSegment

runner = CliRunner()


def test_format_script_removes_empty_lines():
    """format_script should keep non-empty script lines in order."""
    assert format_script("第一句\n\n第二句") == ["第一句", "第二句"]


def test_format_script_removes_note_lines():
    """format_script should remove common manuscript note lines."""
    text = "# 标题\n第一句\n// 备注\n【转场】\n第二句\n[掌声]"
    assert format_script(text) == ["第一句", "第二句"]


def test_match_script_lines_replaces_text_in_order():
    """match_script_lines should keep timing and replace text in order."""
    segments = [{"start_sec": 0.0, "end_sec": 1.0, "text": "旧文本"}]
    result = match_script_lines(segments, ["新文本"])

    assert result[0]["text"] == "新文本"
    assert result[0]["start_sec"] == 0.0


def test_match_script_lines_follow_script_lines():
    """follow-script mode should output one item per script line."""
    segments = [
        {"start_sec": 0.0, "end_sec": 1.0, "text": "旧一"},
        {"start_sec": 1.0, "end_sec": 2.0, "text": "旧二"},
    ]

    result = match_script_lines(
        segments, ["新一", "新二", "新三"], mode="follow_script"
    )

    assert [item["text"] for item in result] == ["新一", "新二", "新三"]
    assert result[-1]["start_sec"] == 1.0
    assert result[-1]["end_sec"] == 2.0


def test_script_format_cli_prints_clean_lines(tmp_path):
    """script format should print cleaned manuscript lines."""
    script = tmp_path / "script.txt"
    script.write_text("# 标题\n第一句\n// 备注\n第二句\n", encoding="utf-8")

    result = runner.invoke(app, ["script", "format", "--script", str(script)])

    assert result.exit_code == 0
    assert result.output.splitlines() == ["第一句", "第二句"]


def test_script_match_cli_writes_jsonl(tmp_path):
    """script match should write timeline-preserving JSONL."""
    timeline = tmp_path / "aligned.jsonl"
    script = tmp_path / "script.txt"
    output = tmp_path / "matched.jsonl"
    timeline.write_text(
        AlignedSegment(
            sentence_id=0,
            start_sec=0.0,
            end_sec=1.0,
            text="旧文本",
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    script.write_text("新文本\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "script",
            "match",
            "--timeline",
            str(timeline),
            "--script",
            str(script),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    matched = AlignedSegment.model_validate_json(output.read_text().strip())
    assert matched.text == "新文本"
    assert matched.start_sec == 0.0
    assert matched.end_sec == 1.0


def test_script_match_cli_writes_report(tmp_path):
    """script match should write a human-readable report next to output."""
    timeline = tmp_path / "aligned.jsonl"
    script = tmp_path / "script.txt"
    output = tmp_path / "matched.jsonl"
    timeline.write_text(
        AlignedSegment(
            sentence_id=0, start_sec=0.0, end_sec=1.0, text="旧文本"
        ).model_dump_json()
        + "\n",
        encoding="utf-8",
    )
    script.write_text("新文本\n额外文本\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "script",
            "match",
            "--timeline",
            str(timeline),
            "--script",
            str(script),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    report = output.with_name("matched_report.md")
    assert "剩余文稿行：1" in report.read_text(encoding="utf-8")
