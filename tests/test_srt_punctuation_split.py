"""SRT punctuation-based split and time interpolation tests."""

from __future__ import annotations

from subtap.core.export import SRTExporter, _smart_split
from subtap.schemas.models import AlignedSegment


def test_split_by_comma():
    """按逗号断句（通过 _smart_split 的逗号+行长度逻辑）。"""
    words = [
        {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "台", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "相", "start_sec": 0.4, "end_sec": 0.6},
        {"word": "机", "start_sec": 0.6, "end_sec": 0.8},
        {"word": "从", "start_sec": 0.8, "end_sec": 1.0},
        {"word": "2015", "start_sec": 1.0, "end_sec": 1.5},
        {"word": "年", "start_sec": 1.5, "end_sec": 1.7},
        {"word": "发", "start_sec": 1.7, "end_sec": 1.9},
        {"word": "布", "start_sec": 1.9, "end_sec": 2.1},
        {"word": "，", "start_sec": 2.1, "end_sec": 2.2},
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
        {"word": "。", "start_sec": 4.5, "end_sec": 4.6},
    ]
    text = "这台相机从2015年发布，一直是一机难求的状态。"
    lines = _smart_split(words, text, max_chars=20)
    assert len(lines) >= 2


def test_split_max_chars():
    """超过 max_chars 时强制断句。"""
    text = "这是一段很长很长很长很长很长很长很长很长很长的文本没有标点符号"
    words = [
        {"word": ch, "start_sec": i * 0.5, "end_sec": (i + 1) * 0.5}
        for i, ch in enumerate(text)
    ]
    lines = _smart_split(words, text, max_chars=20)
    assert len(lines) >= 2
    for line in lines:
        assert len(line["text"]) <= 23  # max_chars + number protection buffer


def test_split_max_chars_keeps_aligner_word_boundaries():
    """强制换行时，使用对齐结果提供的词边界。"""
    words = [
        {"word": "一直是", "start_sec": 0.0, "end_sec": 0.3},
        {"word": "一机难求", "start_sec": 0.3, "end_sec": 0.6},
        {"word": "的状态", "start_sec": 0.6, "end_sec": 0.9},
        {"word": "它叫做", "start_sec": 0.9, "end_sec": 1.2},
        {"word": "理光GR4", "start_sec": 1.2, "end_sec": 1.5},
    ]
    text = "".join(word["word"] for word in words)

    lines = _smart_split(words, text, max_chars=7)

    assert "".join(line["text"] for line in lines) == text
    word_ends = {3, 7, 10, 13, len(text)}
    position = 0
    for line in lines:
        position += len(line["text"])
        assert position in word_ends


def test_no_words_proportional():
    """无 words 时使用传入的 start_sec/end_sec。"""
    text = "一二三四五六七八九十"
    lines = _smart_split([], text, max_chars=20, start_sec=0.0, end_sec=10.0)
    assert len(lines) == 1
    assert lines[0]["start_sec"] == 0.0
    assert lines[0]["end_sec"] == 10.0


def test_srt_exporter_uses_split():
    """SRTExporter.render() 在有 words 时使用 _smart_split 断句。"""
    seg = AlignedSegment(
        sentence_id=0,
        start_sec=0.0,
        end_sec=5.0,
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
    # _smart_split sees no punctuation in words and no meaningful pause,
    # so outputs 1 block. Punctuation stripped: "你好世界"
    assert "你好" in srt
    assert "世界" in srt
    assert "1\n" in srt  # block number 1 exists


def test_srt_exporter_smart_split_with_pause():
    """SRTExporter 在有 words 且存在足够长的暂停时应正确断句。"""
    seg = AlignedSegment(
        sentence_id=0,
        start_sec=0.0,
        end_sec=10.0,
        text="这是第一句。这是第二句。",
        words=[
            {"word": "这", "start_sec": 0.0, "end_sec": 0.2},
            {"word": "是", "start_sec": 0.2, "end_sec": 0.4},
            {"word": "第", "start_sec": 0.4, "end_sec": 0.6},
            {"word": "一", "start_sec": 0.6, "end_sec": 0.8},
            {"word": "句", "start_sec": 0.8, "end_sec": 1.0},
            {"word": "这", "start_sec": 2.5, "end_sec": 2.7},
            {"word": "是", "start_sec": 2.7, "end_sec": 2.9},
            {"word": "第", "start_sec": 2.9, "end_sec": 3.1},
            {"word": "二", "start_sec": 3.1, "end_sec": 3.3},
            {"word": "句", "start_sec": 3.3, "end_sec": 3.5},
        ],
    )
    exporter = SRTExporter()
    srt = exporter.render([seg])
    # 1.5s gap between "句"(1.0) and "这"(2.5) >= pause_threshold 0.3s
    # "这是第一句" ends before a meaningful pause, which should trigger a split
    assert "2\n" in srt  # two subtitle blocks
    assert "第一" in srt
    assert "第二" in srt


def test_itn_applied_in_srt():
    """SRT 导出应应用 ITN 转换。"""
    seg = AlignedSegment(
        sentence_id=0,
        start_sec=0.0,
        end_sec=5.0,
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
