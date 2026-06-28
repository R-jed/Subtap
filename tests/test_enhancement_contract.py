"""Phase 20: 验证 Enhancement 数据契约。"""

from __future__ import annotations

import pytest

from subtap.schemas.enhancement import CleanSegment


def test_clean_segment_has_required_fields():
    """CleanSegment 必须包含所有必需字段。"""
    seg = CleanSegment(
        segment_id=0,
        source_chunk_id=0,
        text="你好世界",
        original_text="你好 世界",
        start_sec=0.0,
        end_sec=2.0,
    )
    assert seg.segment_id == 0
    assert seg.source_chunk_id == 0
    assert seg.text == "你好世界"
    assert seg.original_text == "你好 世界"


def test_clean_segment_timing_immutable_by_convention():
    """CleanSegment 时间字段存在，LLM 不允许修改（通过 convention）。"""
    seg = CleanSegment(
        segment_id=0,
        source_chunk_id=0,
        text="enhanced text",
        original_text="original text",
        start_sec=1.0,
        end_sec=3.0,
    )
    assert seg.start_sec == 1.0
    assert seg.end_sec == 3.0


def test_clean_segment_enhancement_mode_default():
    """CleanSegment enhancement_mode 默认为 local。"""
    seg = CleanSegment(
        segment_id=0,
        source_chunk_id=0,
        text="text",
        original_text="text",
        start_sec=0.0,
        end_sec=1.0,
    )
    assert seg.enhancement_mode == "local"


def test_clean_segment_changed_default():
    """CleanSegment changed 默认为 False。"""
    seg = CleanSegment(
        segment_id=0,
        source_chunk_id=0,
        text="text",
        original_text="text",
        start_sec=0.0,
        end_sec=1.0,
    )
    assert seg.changed is False


def test_clean_segment_rejects_empty_text():
    """CleanSegment 拒绝空文本。"""
    with pytest.raises(ValueError, match="text must not be empty"):
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="",
            original_text="original",
            start_sec=0.0,
            end_sec=1.0,
        )


def test_clean_segment_rejects_invalid_timing():
    """CleanSegment 拒绝无效时间戳。"""
    with pytest.raises(ValueError, match="end_sec must be > start_sec"):
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=2.0,
            end_sec=1.0,
        )


def test_clean_segment_text_changed_detection():
    """CleanSegment.text_changed() 检测文本是否被修改。"""
    seg = CleanSegment(
        segment_id=0,
        source_chunk_id=0,
        text="enhanced",
        original_text="original",
        start_sec=0.0,
        end_sec=1.0,
        changed=True,
    )
    assert seg.text_changed() is True

    seg_same = CleanSegment(
        segment_id=1,
        source_chunk_id=0,
        text="same",
        original_text="same",
        start_sec=0.0,
        end_sec=1.0,
    )
    assert seg_same.text_changed() is False
