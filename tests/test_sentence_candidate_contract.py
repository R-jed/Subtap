"""Phase 20: 验证 SentenceCandidate 数据契约。"""

from __future__ import annotations

import pytest

from subtap.schemas.segmentation import SentenceCandidate


def test_sentence_candidate_has_required_fields():
    """SentenceCandidate 必须包含所有必需字段。"""
    candidate = SentenceCandidate(
        sentence_id=0,
        text="你好世界",
        source_segment_ids=[0, 1],
        start_sec=0.0,
        end_sec=2.0,
    )
    assert candidate.sentence_id == 0
    assert candidate.text == "你好世界"
    assert candidate.source_segment_ids == [0, 1]
    assert candidate.start_sec == 0.0
    assert candidate.end_sec == 2.0


def test_sentence_candidate_auto_computes_cps():
    """SentenceCandidate 自动计算 CPS。"""
    candidate = SentenceCandidate(
        sentence_id=0,
        text="你好世界",  # 4 chars
        source_segment_ids=[0],
        start_sec=0.0,
        end_sec=2.0,
    )
    assert candidate.cps == 2.0  # 4 chars / 2 seconds


def test_sentence_candidate_rejects_empty_text():
    """SentenceCandidate 拒绝空文本。"""
    with pytest.raises(ValueError, match="text must not be empty"):
        SentenceCandidate(
            sentence_id=0,
            text="",
            source_segment_ids=[0],
            start_sec=0.0,
            end_sec=1.0,
        )


def test_sentence_candidate_rejects_invalid_timing():
    """SentenceCandidate 拒绝无效时间戳。"""
    with pytest.raises(ValueError, match="end_sec must be > start_sec"):
        SentenceCandidate(
            sentence_id=0,
            text="text",
            source_segment_ids=[0],
            start_sec=2.0,
            end_sec=1.0,
        )


def test_sentence_candidate_source_trace():
    """SentenceCandidate 保留源 segment 追踪。"""
    candidate = SentenceCandidate(
        sentence_id=0,
        text="合并后的句子",
        source_segment_ids=[0, 1, 2],
        start_sec=0.0,
        end_sec=5.0,
    )
    assert len(candidate.source_segment_ids) == 3
    assert 0 in candidate.source_segment_ids
    assert 2 in candidate.source_segment_ids
