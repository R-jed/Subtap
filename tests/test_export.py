"""Tests for subtitle export layer."""

from __future__ import annotations

from pathlib import Path

from subtap.core.export import (
    SRTExporter,
    ASSExporter,
    TXTExporter,
    _fmt_srt_time,
    _fmt_ass_time,
    run_export,
)
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import AlignedSegment

# ── Time formatting tests ──


def test_fmt_srt_time_basic():
    """SRT time format HH:MM:SS,mmm."""
    assert _fmt_srt_time(0.0) == "00:00:00,000"
    assert _fmt_srt_time(1.5) == "00:00:01,500"
    assert _fmt_srt_time(61.234) == "00:01:01,234"
    assert _fmt_srt_time(3661.0) == "01:01:01,000"


def test_fmt_ass_time_basic():
    """ASS time format H:MM:SS.cc."""
    assert _fmt_ass_time(0.0) == "0:00:00.00"
    assert _fmt_ass_time(1.5) == "0:00:01.50"
    assert _fmt_ass_time(61.23) == "0:01:01.23"
    assert _fmt_ass_time(3661.0) == "1:01:01.00"


# ── SRT export tests ──


def test_srt_render_basic():
    """SRT renders numbered blocks with correct timestamps."""
    segs = [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.5, text="Hello"),
        AlignedSegment(sentence_id=1, start_sec=2.5, end_sec=5.0, text="World"),
    ]
    srt = SRTExporter().render(segs)
    lines = srt.strip().split("\n")
    assert lines[0] == "1"
    assert lines[1] == "00:00:00,000 --> 00:00:02,500"
    assert lines[2] == "Hello"
    assert lines[3] == ""
    assert lines[4] == "2"
    assert lines[5] == "00:00:02,500 --> 00:00:05,000"
    assert lines[6] == "World"


def test_srt_ordering():
    """SRT blocks are ordered by sentence_id."""
    segs = [
        AlignedSegment(sentence_id=2, start_sec=4.0, end_sec=6.0, text="C"),
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.0, text="A"),
        AlignedSegment(sentence_id=1, start_sec=2.0, end_sec=4.0, text="B"),
    ]
    srt = SRTExporter().render(segs)
    # After sorting: block 1=A, block 2=B, block 3=C
    lines = srt.strip().split("\n")
    assert lines[0] == "1"  # block 1
    assert lines[2] == "A"  # first text is A
    assert lines[4] == "2"  # block 2
    assert lines[6] == "B"  # second text is B


def test_srt_utf8_safe():
    """SRT handles UTF-8 characters correctly."""
    segs = [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=1.0, text="你好世界"),
        AlignedSegment(sentence_id=1, start_sec=1.0, end_sec=2.0, text="こんにちは"),
    ]
    srt = SRTExporter().render(segs)
    assert "你好世界" in srt
    assert "こんにちは" in srt


# ── ASS export tests ──


def test_ass_render_basic():
    """ASS renders Dialogue lines with correct format."""
    segs = [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.5, text="Hello"),
    ]
    ass = ASSExporter().render(segs)
    assert "[Script Info]" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,Hello" in ass


def test_ass_newline_escaped():
    """ASS escapes newlines as \\N."""
    segs = [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=1.0, text="Line1\nLine2"),
    ]
    ass = ASSExporter().render(segs)
    assert "Line1\\NLine2" in ass


def test_ass_has_header():
    """ASS output contains required header sections."""
    ass = ASSExporter().render([])
    assert "ScriptType: v4.00+" in ass
    assert "Format: Name, Fontname" in ass


# ── TXT export tests ──


def test_txt_render_basic():
    """TXT renders [start → end] text blocks."""
    segs = [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.5, text="Hello"),
    ]
    txt = TXTExporter().render(segs)
    assert "[00:00:00.000 → 00:00:02.500]" in txt
    assert "Hello" in txt


def test_txt_multiline():
    """TXT handles multiple segments."""
    segs = [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=1.0, text="A"),
        AlignedSegment(sentence_id=1, start_sec=1.0, end_sec=2.0, text="B"),
    ]
    txt = TXTExporter().render(segs)
    assert "A" in txt
    assert "B" in txt


# ── Pipeline integration tests ──


def _make_aligned_jsonl(ws: Workspace, texts: list[str]) -> None:
    """Write mock AlignedSegments to aligned.jsonl."""
    ws.ensure_dirs()
    with open(ws.aligned_jsonl, "w") as f:
        for i, text in enumerate(texts):
            seg = AlignedSegment(
                sentence_id=i,
                start_sec=float(i),
                end_sec=float(i + 1),
                text=text,
            )
            f.write(seg.model_dump_json() + "\n")


def test_run_export_srt(test_config: SubtapConfig, tmp_path: Path):
    """run_export produces valid SRT file."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_aligned_jsonl(ws, ["Hello", "World"])

    out_dir = tmp_path / "output"
    result = run_export(ws.aligned_jsonl, out_dir, fmt="srt")

    assert Path(result["output_path"]).exists()
    assert result["format"] == "srt"
    assert result["segment_count"] == 2

    content = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "Hello" in content
    assert "World" in content
    assert "-->" in content


def test_run_export_ass(test_config: SubtapConfig, tmp_path: Path):
    """run_export produces valid ASS file."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_aligned_jsonl(ws, ["Test"])

    out_dir = tmp_path / "output"
    result = run_export(ws.aligned_jsonl, out_dir, fmt="ass")

    content = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "Dialogue:" in content


def test_run_export_txt(test_config: SubtapConfig, tmp_path: Path):
    """run_export produces valid TXT file."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_aligned_jsonl(ws, ["Plain text"])

    out_dir = tmp_path / "output"
    result = run_export(ws.aligned_jsonl, out_dir, fmt="txt")

    content = Path(result["output_path"]).read_text(encoding="utf-8")
    assert "Plain text" in content
    assert "→" in content


def test_run_export_unknown_format(test_config: SubtapConfig, tmp_path: Path):
    """run_export raises ValueError for unknown format."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_aligned_jsonl(ws, ["Test"])

    try:
        run_export(ws.aligned_jsonl, tmp_path / "out", fmt="vtt")
        assert False
    except ValueError as e:
        assert "vtt" in str(e)


def test_multi_format_consistency(test_config: SubtapConfig, tmp_path: Path):
    """All formats produce files for the same input."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_aligned_jsonl(ws, ["Consistency test"])

    out_dir = tmp_path / "output"
    for fmt in ["srt", "ass", "txt"]:
        result = run_export(ws.aligned_jsonl, out_dir, fmt=fmt, stem=f"output_{fmt}")
        assert Path(result["output_path"]).exists()


def test_cli_export_runnable(test_config: SubtapConfig, tmp_path: Path, monkeypatch):
    """CLI export command runs without crash."""
    from typer.testing import CliRunner
    from subtap.cli import app

    ws = Workspace(test_config, base_dir=tmp_path / "work")
    _make_aligned_jsonl(ws, ["CLI export test"])

    out_dir = tmp_path / "cli_output"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "export",
            str(ws.aligned_jsonl),
            "-o",
            str(out_dir),
            "-f",
            "srt",
        ],
    )
    assert result.exit_code == 0
    assert "完成" in result.output
