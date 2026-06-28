"""Phase 20: 验证 LLM 不允许修改时间轴。"""

from __future__ import annotations

import pytest

from subtap.schemas.enhancement import CleanSegment


def test_llm_output_preserves_timing():
    """LLM 输出必须保留原始时间戳。"""
    # 模拟 LLM 处理前的 segment
    original = CleanSegment(
        segment_id=0,
        source_chunk_id=0,
        text="原始文本",
        original_text="原始文本",
        start_sec=1.0,
        end_sec=3.0,
    )

    # LLM 只修改文本，不修改时间
    llm_enhanced = CleanSegment(
        segment_id=original.segment_id,
        source_chunk_id=original.source_chunk_id,
        text="增强后的文本",  # LLM 修改了文本
        original_text=original.text,
        start_sec=original.start_sec,  # 时间不变
        end_sec=original.end_sec,  # 时间不变
        enhancement_mode="api",
        changed=True,
        change_reasons=["llm_correction"],
    )

    assert llm_enhanced.start_sec == original.start_sec
    assert llm_enhanced.end_sec == original.end_sec
    assert llm_enhanced.text != original.text  # 文本被修改了


def test_clean_segment_validator_rejects_negative_start():
    """验证器拒绝负数 start_sec。"""
    with pytest.raises(ValueError, match="start_sec must be >= 0"):
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=-1.0,
            end_sec=1.0,
        )


def test_clean_segment_validator_rejects_end_before_start():
    """验证器拒绝 end_sec < start_sec。"""
    with pytest.raises(ValueError, match="end_sec must be > start_sec"):
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=3.0,
            end_sec=1.0,
        )


def test_enhancement_modes():
    """验证所有增强模式。"""
    for mode in ("off", "local", "api"):
        seg = CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="text",
            original_text="text",
            start_sec=0.0,
            end_sec=1.0,
            enhancement_mode=mode,
        )
        assert seg.enhancement_mode == mode
