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


# ── _inject_punct tests ──


def test_inject_punct_basic_single_char_words():
    """单字词 + 逗号：逗号应在正确位置。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "照", "start_sec": 44.0, "end_sec": 44.2},
        {"word": "片", "start_sec": 44.2, "end_sec": 44.5},
        {"word": "但", "start_sec": 44.8, "end_sec": 45.0},
        {"word": "是", "start_sec": 45.0, "end_sec": 45.1},
        {"word": "卖", "start_sec": 45.2, "end_sec": 45.5},
    ]
    result = _inject_punct(words, "照片,但是卖")
    seq = [w["word"] for w in result]
    assert seq == ["照", "片", ",", "但", "是", "卖"]


def test_inject_punct_multi_char_words():
    """多字词 + 逗号。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "照片", "start_sec": 44.0, "end_sec": 44.5},
        {"word": "但是", "start_sec": 44.8, "end_sec": 45.1},
        {"word": "卖", "start_sec": 45.2, "end_sec": 45.5},
    ]
    result = _inject_punct(words, "照片,但是卖")
    seq = [w["word"] for w in result]
    assert seq == ["照片", ",", "但是", "卖"]


def test_inject_punct_missing_word_in_list():
    """词列表缺失字符时，标点应在正确位置（不被错位到后面的词之间）。

    核心 bug 场景：words 缺少'片'，text='照片,但是卖'
    逗号应在'照'之后，而不是'但'和'是'之间。
    """
    from subtap.core.export import _inject_punct
    words = [
        {"word": "照", "start_sec": 44.0, "end_sec": 44.2},
        {"word": "但", "start_sec": 44.8, "end_sec": 45.0},
        {"word": "是", "start_sec": 45.0, "end_sec": 45.1},
        {"word": "卖", "start_sec": 45.2, "end_sec": 45.5},
    ]
    result = _inject_punct(words, "照片,但是卖")
    seq = [w["word"] for w in result]
    # 逗号应在'照'之后（因为'片'缺失，逗号在文本中紧跟'片'之后，
    # 而'片'之前是'照'，所以逗号应在最后一个匹配词'照'之后）
    assert seq == ["照", ",", "但", "是", "卖"]


def test_inject_punct_sentence_end_punct():
    """句末标点应正确插入。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "好", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "的", "start_sec": 1.3, "end_sec": 1.5},
    ]
    result = _inject_punct(words, "好的。")
    seq = [w["word"] for w in result]
    assert seq == ["好的", "。"] or seq == ["好", "的", "。"]


def test_inject_punct_multiple_puncts():
    """多个连续标点。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "哇", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "好", "start_sec": 1.5, "end_sec": 1.7},
    ]
    result = _inject_punct(words, "哇！好")
    seq = [w["word"] for w in result]
    assert seq == ["哇", "！", "好"]


def test_inject_punct_punct_at_start():
    """标点在文本开头。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "好", "start_sec": 1.0, "end_sec": 1.2},
    ]
    result = _inject_punct(words, "，好")
    seq = [w["word"] for w in result]
    assert seq == ["，", "好"]


def test_inject_punct_no_punct():
    """无标点时保持原样。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "你好", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "世界", "start_sec": 1.3, "end_sec": 1.5},
    ]
    result = _inject_punct(words, "你好世界")
    seq = [w["word"] for w in result]
    assert seq == ["你好", "世界"]


def test_inject_punct_timestamp_interpolation():
    """标点时间戳应在前后词之间插值。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "照", "start_sec": 44.0, "end_sec": 44.2},
        {"word": "片", "start_sec": 44.2, "end_sec": 44.5},
        {"word": "但", "start_sec": 44.8, "end_sec": 45.0},
        {"word": "是", "start_sec": 45.0, "end_sec": 45.1},
    ]
    result = _inject_punct(words, "照片,但是")
    comma = [w for w in result if w["word"] == ","][0]
    # 逗号时间应在 44.5 和 44.8 之间
    assert 44.5 <= comma["start_sec"] <= 44.8
    assert comma["start_sec"] == comma["end_sec"]


def test_inject_punct_missing_word_after_punct():
    """缺失词在标点之后：标点仍应在正确位置。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "照", "start_sec": 44.0, "end_sec": 44.2},
        {"word": "片", "start_sec": 44.2, "end_sec": 44.5},
        {"word": "是", "start_sec": 45.0, "end_sec": 45.1},
        {"word": "卖", "start_sec": 45.2, "end_sec": 45.5},
    ]
    # text = '照片,但是卖', 缺少'但'
    result = _inject_punct(words, "照片,但是卖")
    seq = [w["word"] for w in result]
    assert seq == ["照", "片", ",", "是", "卖"]


def test_inject_punct_consecutive_punct():
    """连续多个标点应全部保留。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "哇", "start_sec": 1.0, "end_sec": 1.2},
        {"word": "好", "start_sec": 1.5, "end_sec": 1.7},
    ]
    result = _inject_punct(words, "哇！！好")
    seq = [w["word"] for w in result]
    assert seq == ["哇", "！", "！", "好"]


def test_inject_punct_missing_word_with_trailing_punct():
    """缺失词 + 结尾标点。"""
    from subtap.core.export import _inject_punct
    words = [
        {"word": "好", "start_sec": 1.0, "end_sec": 1.2},
    ]
    # text = '好的。', '的'缺失，句号在结尾
    result = _inject_punct(words, "好的。")
    seq = [w["word"] for w in result]
    assert seq == ["好", "。"]


def test_inject_punct_empty_input():
    """空输入应返回空列表。"""
    from subtap.core.export import _inject_punct
    assert _inject_punct([], "") == []
