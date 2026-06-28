"""Phase 20: 验证 AlignedSubtitle 数据契约。"""

from __future__ import annotations

import pytest

from subtap.schemas.alignment import AlignedSubtitle, AlignedWord


def test_aligned_subtitle_has_required_fields():
    """AlignedSubtitle 必须包含所有必需字段。"""
    sub = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=2.0,
        text="你好世界",
    )
    assert sub.subtitle_id == 0
    assert sub.start_sec == 0.0
    assert sub.end_sec == 2.0
    assert sub.text == "你好世界"


def test_aligned_subtitle_words_optional():
    """AlignedSubtitle words 字段可选。"""
    sub = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=2.0,
        text="test",
    )
    assert sub.words == []


def test_aligned_subtitle_with_word_timing():
    """AlignedSubtitle 可以包含词级时间戳。"""
    words = [
        AlignedWord(word="你好", start_sec=0.0, end_sec=0.5),
        AlignedWord(word="世界", start_sec=0.5, end_sec=1.0),
    ]
    sub = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="你好世界",
        words=words,
        alignment_confidence=0.95,
    )
    assert len(sub.words) == 2
    assert sub.alignment_confidence == 0.95


def test_aligned_subtitle_rejects_empty_text():
    """AlignedSubtitle 拒绝空文本。"""
    with pytest.raises(ValueError, match="text must not be empty"):
        AlignedSubtitle(
            subtitle_id=0,
            start_sec=0.0,
            end_sec=1.0,
            text="",
        )


def test_aligned_subtitle_rejects_invalid_timing():
    """AlignedSubtitle 拒绝无效时间戳。"""
    with pytest.raises(ValueError, match="end_sec must be > start_sec"):
        AlignedSubtitle(
            subtitle_id=0,
            start_sec=2.0,
            end_sec=1.0,
            text="text",
        )


def test_aligned_subtitle_duration():
    """AlignedSubtitle.duration_sec() 返回正确时长。"""
    sub = AlignedSubtitle(
        subtitle_id=0,
        start_sec=1.0,
        end_sec=3.5,
        text="test",
    )
    assert sub.duration_sec() == 2.5


def test_aligned_subtitle_cps():
    """AlignedSubtitle.cps() 返回正确的 CPS。"""
    sub = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.0,
        end_sec=2.0,
        text="你好世界",  # 4 chars
    )
    assert sub.cps() == 2.0  # 4 chars / 2 seconds


def test_aligned_subtitle_is_final_timing_source():
    """AlignedSubtitle 是最终时间轴的唯一来源。"""
    sub = AlignedSubtitle(
        subtitle_id=0,
        start_sec=0.5,
        end_sec=2.5,
        text="最终时间轴",
    )
    # 这些时间戳是 ForcedAligner 产生的最终值
    assert sub.start_sec == 0.5
    assert sub.end_sec == 2.5
