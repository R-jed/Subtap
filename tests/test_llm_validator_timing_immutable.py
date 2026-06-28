"""Phase 21: 验证 LLM 验证器强制时间戳不可变。"""

from __future__ import annotations

import pytest

from subtap.enhancement.validator import EnhancementValidator
from subtap.schemas.enhancement import CleanSegment


def test_validator_passes_when_timing_unchanged():
    """时间戳不变时验证通过。"""
    validator = EnhancementValidator()
    original = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="original",
            original_text="original",
            start_sec=1.0,
            end_sec=3.0,
        )
    ]
    enhanced = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="enhanced",
            original_text="original",
            start_sec=1.0,
            end_sec=3.0,
        )
    ]
    result = validator.validate(original, enhanced)
    assert result.valid is True


def test_validator_fails_when_start_sec_changed():
    """start_sec 改变时验证失败。"""
    validator = EnhancementValidator()
    original = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=1.0,
            end_sec=3.0,
        )
    ]
    enhanced = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=2.0,  # Changed!
            end_sec=3.0,
        )
    ]
    result = validator.validate(original, enhanced)
    assert result.valid is False
    assert any("start_sec" in e for e in result.errors)


def test_validator_fails_when_end_sec_changed():
    """end_sec 改变时验证失败。"""
    validator = EnhancementValidator()
    original = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=1.0,
            end_sec=3.0,
        )
    ]
    enhanced = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=1.0,
            end_sec=5.0,  # Changed!
        )
    ]
    result = validator.validate(original, enhanced)
    assert result.valid is False
    assert any("end_sec" in e for e in result.errors)


def test_clean_segment_rejects_empty_text():
    """CleanSegment 拒绝空文本（schema 级别验证）。"""
    with pytest.raises(ValueError, match="text must not be empty"):
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="",  # Empty!
            original_text="text",
            start_sec=0.0,
            end_sec=1.0,
        )


def test_validator_fails_on_count_mismatch():
    """段落数量不匹配时验证失败。"""
    validator = EnhancementValidator()
    original = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=0.0,
            end_sec=1.0,
        )
    ]
    enhanced = []  # Empty!
    result = validator.validate(original, enhanced)
    assert result.valid is False
    assert any("mismatch" in e.lower() for e in result.errors)
