"""Phase 21: 验证 API 增强（mock）。"""

from __future__ import annotations

from subtap.enhancement.api_llm import APIEnhancer
from subtap.enhancement.base import EnhancementMode
from subtap.schemas.enhancement import CleanSegment


def test_api_enhancer_mode():
    """APIEnhancer 模式为 API。"""
    enhancer = APIEnhancer()
    assert enhancer.mode == EnhancementMode.API


def test_api_enhancer_default_config():
    """APIEnhancer 默认配置。"""
    enhancer = APIEnhancer()
    assert enhancer.provider == "openai_compatible"
    assert enhancer.model == "gpt-4.1-mini"


def test_api_enhancer_preserves_timing():
    """API 增强不应修改时间戳。"""
    enhancer = APIEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="test text",
            original_text="test text",
            start_sec=1.0,
            end_sec=3.0,
        )
    ]
    result = enhancer.enhance(segments)
    assert result.segments[0].start_sec == 1.0
    assert result.segments[0].end_sec == 3.0


def test_api_enhancer_mode_is_api():
    """API 增强结果模式为 API。"""
    enhancer = APIEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="test",
            original_text="test",
            start_sec=0.0,
            end_sec=1.0,
        )
    ]
    result = enhancer.enhance(segments)
    assert result.mode == EnhancementMode.API


def test_api_enhancer_tracks_api_calls():
    """API 增强应跟踪 API 调用次数。"""
    enhancer = APIEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="test",
            original_text="test",
            start_sec=0.0,
            end_sec=1.0,
        )
    ]
    result = enhancer.enhance(segments)
    assert result.api_calls > 0


def test_api_enhancer_custom_provider():
    """APIEnhancer 支持自定义 provider。"""
    enhancer = APIEnhancer(
        provider="anthropic_compatible",
        model="claude-3-sonnet",
    )
    assert enhancer.provider == "anthropic_compatible"
    assert enhancer.model == "claude-3-sonnet"
