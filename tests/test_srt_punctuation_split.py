"""SRT punctuation-based split and time interpolation tests."""

from __future__ import annotations

from subtap.core.export import SRTExporter, _split_subtitle_lines
from subtap.schemas.models import AlignedSegment


def test_split_by_comma():
    """按逗号断句。"""
    seg = AlignedSegment(
        sentence_id=0, start_sec=0.0, end_sec=5.0,
        text="这台相机从2015年发布，一直是一机难求的状态。",
        words=[
            {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
            {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
            {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
            {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
            {"word": "从", "start_sec": 0.8, "end_sec": 1.0},
            {"word": "2015", "start_sec": 1.0, "end_sec": 1.5},
            {"word": "年", "start_sec": 1.5, "end_sec": 1.7},
            {"word": "发", "start_sec": 1.7, "end_sec": 1.9},
            {"word": "布", "start_sec": 1.9, "end_sec": 2.1},
            {"word": "一", "start_sec": 2.5, "end_sec": 2.7},
            {"word": "直", "start_sec": 2.7, "end_sec": 2.9},
            {"word": "是", "start_sec": 2.9, "end_sec": 3.1},
            {"word": "一", "start_sec": 3.1, "end_sec": 3.3},
            {"word": "机", "start_sec": 3.3, "end_sec": 3.5},
            {"word": "难", "start_sec": 3.5, "end_sec": 3.7},
            {"word": "求", "start_sec": 3.7, "end_sec": 3.9},
            {"word": "的", "start_sec": 3.9, "end_sec": 4.1},
            {"word": "状", "start_sec": 4.1, "end_sec": 4.3},
            {"word": "态", "start_sec": 4.3, "end_sec": 4.5},
        ],
    )
    lines = _split_subtitle_lines(seg.text, seg.words, seg.start_sec, seg.end_sec, max_chars=20)
    assert len(lines) >= 2
    # First line should contain the comma
    assert "，" in lines[0]["text"] or "发布" in lines[0]["text"]


def test_split_max_chars():
    """超过 max_chars 时强制断句。"""
    seg = AlignedSegment(
        sentence_id=0, start_sec=0.0, end_sec=10.0,
        text="这是一段很长很长很长很长很长很长很长很长很长的文本没有标点符号",
        words=[
            {"word": ch, "start_sec": i * 0.5, "end_sec": (i + 1) * 0.5}
            for i, ch in enumerate("这是一段很长很长很长很长很长很长很长很长很长的文本没有标点符号")
        ],
    )
    lines = _split_subtitle_lines(seg.text, seg.words, seg.start_sec, seg.end_sec, max_chars=20)
    for line in lines:
        clean = line["text"].replace("，", "").replace("。", "").replace("、", "")
        assert len(clean) <= 20, f"Line too long: '{line['text']}' ({len(clean)} chars)"


def test_no_words_proportional():
    """无 words 时按字数比例分配时间。"""
    seg = AlignedSegment(
        sentence_id=0, start_sec=0.0, end_sec=10.0,
        text="一二三四五，六七八九十。",
        words=[],
    )
    lines = _split_subtitle_lines(seg.text, seg.words, seg.start_sec, seg.end_sec, max_chars=20)
    assert len(lines) == 2
    assert lines[0]["start_sec"] == 0.0
    assert lines[-1]["end_sec"] == 10.0


def test_srt_exporter_uses_split():
    """SRTExporter.render() 应使用断句逻辑。"""
    seg = AlignedSegment(
        sentence_id=0, start_sec=0.0, end_sec=5.0,
        text="你好，世界。",
        words=[
            {"word": "你", "start_sec": 0.0, "end_sec": 0.5},
            {"word": "好", "start_sec": 0.5, "end_sec": 1.0},
            {"word": "世", "start_sec": 2.0, "end_sec": 2.5},
            {"word": "界", "start_sec": 2.5, "end_sec": 3.0},
        ],
    )
    exporter = SRTExporter()
    srt = exporter.render([seg])
    lines = srt.strip().split("\n")
    # Should have 2 subtitle blocks (split at comma)
    assert "你好，" in srt
    assert "世界。" in srt
    assert "2\n" in srt  # block number 2 exists


def test_itn_applied_in_srt():
    """SRT 导出应应用 ITN 转换。"""
    seg = AlignedSegment(
        sentence_id=0, start_sec=0.0, end_sec=5.0,
        text="二零一五年发布。",
        words=[
            {"word": "二", "start_sec": 0.0, "end_sec": 0.2},
            {"word": "零", "start_sec": 0.2, "end_sec": 0.4},
            {"word": "一", "start_sec": 0.4, "end_sec": 0.6},
            {"word": "五", "start_sec": 0.6, "end_sec": 0.8},
            {"word": "年", "start_sec": 0.8, "end_sec": 1.0},
            {"word": "发", "start_sec": 1.0, "end_sec": 1.2},
            {"word": "布", "start_sec": 1.2, "end_sec": 1.4},
        ],
    )
    exporter = SRTExporter()
    srt = exporter.render([seg])
    assert "2015" in srt