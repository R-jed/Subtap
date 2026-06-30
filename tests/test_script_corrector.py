"""Tests for script corrector."""
from subtap.script.corrector import (
    CorrectionResult,
    correct_text,
    correct_segments,
    CORRECTION_THRESHOLD,
)
from subtap.script.aligner import AlignOp


def test_fixes_typo():
    result = correct_text("一击难求", "一机难求")
    assert result.corrected_flag is True
    assert result.corrected == "一机难求"


def test_fixes_name():
    # 相似度低于阈值，保留原文
    result = correct_text("李光机亚四", "理光GR四")
    assert result.similarity < CORRECTION_THRESHOLD
    assert result.corrected_flag is False
    assert result.corrected == "李光机亚四"


def test_above_threshold_corrects():
    # 相似度高于阈值，纠正
    result = correct_text("今天天气真好", "今天天气很好")
    assert result.similarity >= CORRECTION_THRESHOLD
    assert result.corrected_flag is True
    assert result.corrected == "今天天气很好"


def test_below_threshold_preserves():
    result = correct_text("完全不同的句子A", "XYZ")
    assert result.similarity < CORRECTION_THRESHOLD
    assert result.corrected_flag is False
    assert result.corrected == "完全不同的句子A"


def test_equal_no_change():
    result = correct_text("相同文本", "相同文本")
    assert result.similarity == 1.0
    assert result.corrected_flag is False
    assert result.corrected == "相同文本"


def test_segments_batch():
    segments = [
        {"text": "一击难求", "start_sec": 0.0, "end_sec": 2.0},
        {"text": "正常文本", "start_sec": 2.0, "end_sec": 4.0},
    ]
    ref_lines = ["一机难求", "正常文本"]
    ops = [
        AlignOp("replace", 0, 0),
        AlignOp("equal", 1, 1),
    ]
    result, skipped = correct_segments(segments, ops, ref_lines, mode="follow_script")
    assert result[0]["text"] == "一机难求"
    assert result[1]["text"] == "正常文本"
    assert skipped == 0