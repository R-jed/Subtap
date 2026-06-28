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


# ── Fragment merge tests ──


def test_merge_fragments_merges_short_lines():
    """碎片行（≤2字）应被合并到上一行。"""
    from subtap.core.export import _merge_fragments
    lines = [
        {"text": "这是一句完整的话", "start_sec": 1.0, "end_sec": 2.0},
        {"text": "我们", "start_sec": 2.0, "end_sec": 2.5},
        {"text": "继续下一句", "start_sec": 2.5, "end_sec": 3.0},
    ]
    result = _merge_fragments(lines)
    assert len(result) == 2
    assert result[0]["text"] == "这是一句完整的话我们"
    assert result[0]["start_sec"] == 1.0
    assert result[0]["end_sec"] == 2.5


def test_merge_fragments_filters_empty():
    """空文本行应被过滤。"""
    from subtap.core.export import _merge_fragments
    lines = [
        {"text": "第一句", "start_sec": 1.0, "end_sec": 2.0},
        {"text": "", "start_sec": 2.0, "end_sec": 2.5},
        {"text": "第二句", "start_sec": 2.5, "end_sec": 3.0},
    ]
    result = _merge_fragments(lines)
    assert len(result) == 2
    assert result[0]["text"] == "第一句"
    assert result[1]["text"] == "第二句"


def test_merge_fragments_merges_tail_particle():
    """以虚词结尾的行应与下一行合并。"""
    from subtap.core.export import _merge_fragments
    lines = [
        {"text": "核心的", "start_sec": 1.0, "end_sec": 2.0},
        {"text": "点是这个虚化", "start_sec": 2.0, "end_sec": 3.0},
    ]
    result = _merge_fragments(lines)
    assert len(result) == 1
    assert result[0]["text"] == "核心的点是这个虚化"


def test_merge_fragments_merges_filler():
    """语气词独立成行应被合并到上一行。"""
    from subtap.core.export import _merge_fragments
    lines = [
        {"text": "我觉得不太好", "start_sec": 1.0, "end_sec": 2.0},
        {"text": "呃", "start_sec": 2.0, "end_sec": 2.2},
        {"text": "应该是这样的", "start_sec": 2.2, "end_sec": 3.0},
    ]
    result = _merge_fragments(lines)
    assert len(result) == 2
    assert result[0]["text"] == "我觉得不太好呃"


def test_merge_fragments_no_merge_for_normal():
    """正常长度的行不应被合并。"""
    from subtap.core.export import _merge_fragments
    lines = [
        {"text": "这是一句正常的话", "start_sec": 1.0, "end_sec": 2.0},
        {"text": "这是另一句正常的话", "start_sec": 2.0, "end_sec": 3.0},
    ]
    result = _merge_fragments(lines)
    assert len(result) == 2


def test_srt_render_merges_fragments():
    """SRT 渲染应自动合并碎片行。"""
    from subtap.core.export import SRTExporter
    from subtap.schemas.models import AlignedSegment
    segs = [
        AlignedSegment(
            sentence_id=0, start_sec=1.0, end_sec=3.0,
            text="核心的点是这个", words=[
                {"word": "核", "start_sec": 1.0, "end_sec": 1.1},
                {"word": "心", "start_sec": 1.1, "end_sec": 1.2},
                {"word": "的", "start_sec": 1.2, "end_sec": 1.3},
                {"word": "点", "start_sec": 1.5, "end_sec": 1.6},
                {"word": "是", "start_sec": 1.6, "end_sec": 1.7},
                {"word": "这", "start_sec": 1.7, "end_sec": 1.8},
                {"word": "个", "start_sec": 1.8, "end_sec": 1.9},
            ],
        ),
    ]
    srt = SRTExporter(punctuation=False).render(segs)
    # "核心的" 以 "的" 结尾，应被合并到下一行
    # 最终输出不应有 "核心的" 单独一行
    content_lines = [l for l in srt.split("\n") if l.strip() and "-->" not in l and not l.strip().isdigit()]
    for line in content_lines:
        assert line != "核心的", f"'核心的' 不应单独成行: {srt}"


def test_srt_render_filters_empty_segments():
    """SRT 渲染应过滤空文本段。"""
    from subtap.core.export import SRTExporter
    from subtap.schemas.models import AlignedSegment
    segs = [
        AlignedSegment(sentence_id=0, start_sec=1.0, end_sec=2.0, text="正常内容"),
        AlignedSegment(sentence_id=1, start_sec=2.0, end_sec=2.5, text=""),
        AlignedSegment(sentence_id=2, start_sec=2.5, end_sec=3.0, text="更多内容"),
    ]
    srt = SRTExporter(punctuation=False).render(segs)
    time_lines = [l for l in srt.split("\n") if "-->" in l]
    assert len(time_lines) == 2


# ── _smart_split tests ──


def test_smart_split_basic():
    """基本断句：句末标点 + 停顿 + 宽度限制。"""
    from subtap.core.export import _smart_split
    words = [
        {"word": "这", "start_sec": 1.0, "end_sec": 1.1},
        {"word": "是", "start_sec": 1.1, "end_sec": 1.2},
        {"word": "第", "start_sec": 1.2, "end_sec": 1.3},
        {"word": "一", "start_sec": 1.3, "end_sec": 1.4},
        {"word": "句", "start_sec": 1.4, "end_sec": 1.5},
        {"word": "。", "start_sec": 1.5, "end_sec": 1.6},
        {"word": "这", "start_sec": 2.0, "end_sec": 2.1},
        {"word": "是", "start_sec": 2.1, "end_sec": 2.2},
        {"word": "第", "start_sec": 2.2, "end_sec": 2.3},
        {"word": "二", "start_sec": 2.3, "end_sec": 2.4},
        {"word": "句", "start_sec": 2.4, "end_sec": 2.5},
    ]
    result = _smart_split(words, "这是第一句。这是第二句")
    assert len(result) == 2
    assert result[0]["text"] == "这是第一句"
    assert result[1]["text"] == "这是第二句"


def test_smart_split_pause_break():
    """停顿断句：停顿 > 0.3s 应产生新字幕。"""
    from subtap.core.export import _smart_split
    words = [
        {"word": "前", "start_sec": 1.0, "end_sec": 1.1},
        {"word": "半", "start_sec": 1.1, "end_sec": 1.2},
        {"word": "句", "start_sec": 1.2, "end_sec": 1.3},
        {"word": "后", "start_sec": 2.0, "end_sec": 2.1},
        {"word": "半", "start_sec": 2.1, "end_sec": 2.2},
        {"word": "句", "start_sec": 2.2, "end_sec": 2.3},
    ]
    result = _smart_split(words, "前半句后半句", min_chars=2)
    assert len(result) == 2


def test_smart_split_max_chars():
    """宽度限制：超过 max_chars 应换行。"""
    from subtap.core.export import _smart_split
    words = [
        {"word": "这", "start_sec": 1.0, "end_sec": 1.1},
        {"word": "是", "start_sec": 1.1, "end_sec": 1.2},
        {"word": "一", "start_sec": 1.2, "end_sec": 1.3},
        {"word": "个", "start_sec": 1.3, "end_sec": 1.4},
        {"word": "很", "start_sec": 1.4, "end_sec": 1.5},
        {"word": "长", "start_sec": 1.5, "end_sec": 1.6},
        {"word": "的", "start_sec": 1.6, "end_sec": 1.7},
        {"word": "句", "start_sec": 1.7, "end_sec": 1.8},
        {"word": "子", "start_sec": 1.8, "end_sec": 1.9},
        {"word": "需", "start_sec": 1.9, "end_sec": 2.0},
        {"word": "要", "start_sec": 2.0, "end_sec": 2.1},
        {"word": "换", "start_sec": 2.1, "end_sec": 2.2},
        {"word": "行", "start_sec": 2.2, "end_sec": 2.3},
    ]
    result = _smart_split(words, "这是一个很长的句子需要换行", max_chars=10)
    assert len(result) >= 2
    for line in result:
        assert len(line["text"]) <= 13


def test_smart_split_number_protection():
    """数字序列保护：不拆分连续数字。"""
    from subtap.core.export import _smart_split
    words = [
        {"word": "价", "start_sec": 1.0, "end_sec": 1.1},
        {"word": "格", "start_sec": 1.1, "end_sec": 1.2},
        {"word": "是", "start_sec": 1.2, "end_sec": 1.3},
        {"word": "一", "start_sec": 1.3, "end_sec": 1.4},
        {"word": "万", "start_sec": 1.4, "end_sec": 1.5},
        {"word": "两", "start_sec": 1.5, "end_sec": 1.6},
        {"word": "千", "start_sec": 1.6, "end_sec": 1.7},
        {"word": "九", "start_sec": 1.7, "end_sec": 1.8},
        {"word": "百", "start_sec": 1.8, "end_sec": 1.9},
        {"word": "九", "start_sec": 1.9, "end_sec": 2.0},
        {"word": "十", "start_sec": 2.0, "end_sec": 2.1},
        {"word": "九", "start_sec": 2.1, "end_sec": 2.2},
    ]
    result = _smart_split(words, "价格是一万两千九百九十九", max_chars=8)
    num_line = [l for l in result if "万" in l["text"]]
    assert len(num_line) == 1
    assert "一万两千九百九十九" in num_line[0]["text"]


def test_smart_split_filler_merge():
    """语气词应合并到上一行。"""
    from subtap.core.export import _smart_split
    words = [
        {"word": "我", "start_sec": 1.0, "end_sec": 1.1},
        {"word": "觉", "start_sec": 1.1, "end_sec": 1.2},
        {"word": "得", "start_sec": 1.2, "end_sec": 1.3},
        {"word": "呃", "start_sec": 1.5, "end_sec": 1.6},
        {"word": "应", "start_sec": 2.0, "end_sec": 2.1},
        {"word": "该", "start_sec": 2.1, "end_sec": 2.2},
        {"word": "是", "start_sec": 2.2, "end_sec": 2.3},
    ]
    result = _smart_split(words, "我觉得呃应该是", min_chars=2)
    for line in result:
        assert line["text"] != "呃"
