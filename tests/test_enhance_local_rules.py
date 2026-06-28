"""Phase 21: 验证本地规则增强。"""

from __future__ import annotations

from subtap.enhancement.local_rules import LocalRulesEnhancer
from subtap.enhancement.base import EnhancementMode
from subtap.schemas.enhancement import CleanSegment


def test_local_enhancer_mode():
    """LocalRulesEnhancer 模式为 LOCAL。"""
    enhancer = LocalRulesEnhancer()
    assert enhancer.mode == EnhancementMode.LOCAL


def test_local_enhancer_normalizes_unicode():
    """本地增强应进行 Unicode 规范化。"""
    enhancer = LocalRulesEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="Ｈｅｌｌｏ",  # Full-width
            original_text="Ｈｅｌｌｏ",
            start_sec=0.0,
            end_sec=1.0,
        )
    ]
    result = enhancer.enhance(segments)
    # NFKC normalization should convert full-width to ASCII
    assert result.segments[0].text == "Hello"


def test_local_enhancer_converts_fullwidth_digits():
    """本地增强应转换全角数字。"""
    enhancer = LocalRulesEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="１２３４５",
            original_text="１２３４５",
            start_sec=0.0,
            end_sec=1.0,
        )
    ]
    result = enhancer.enhance(segments)
    assert result.segments[0].text == "12345"


def test_local_enhancer_cleans_whitespace():
    """本地增强应清理多余空白。"""
    enhancer = LocalRulesEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="  hello   world  ",
            original_text="  hello   world  ",
            start_sec=0.0,
            end_sec=1.0,
        )
    ]
    result = enhancer.enhance(segments)
    assert result.segments[0].text == "hello world"


def test_local_enhancer_applies_glossary():
    """本地增强应应用术语表。"""
    enhancer = LocalRulesEnhancer()
    glossary = {"错词": "正确词"}
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="这是错词",
            original_text="这是错词",
            start_sec=0.0,
            end_sec=1.0,
        )
    ]
    result = enhancer.enhance(segments, glossary=glossary)
    assert result.segments[0].text == "这是正确词"


def test_local_enhancer_preserves_timing():
    """本地增强不应修改时间戳。"""
    enhancer = LocalRulesEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="test",
            original_text="test",
            start_sec=1.0,
            end_sec=3.0,
        )
    ]
    result = enhancer.enhance(segments)
    assert result.segments[0].start_sec == 1.0
    assert result.segments[0].end_sec == 3.0


def test_local_enhancer_counts_changes():
    """本地增强应统计修改数量。"""
    enhancer = LocalRulesEnhancer()
    segments = [
        CleanSegment(
            segment_id=0,
            source_chunk_id=0,
            text="  test  ",
            original_text="  test  ",
            start_sec=0.0,
            end_sec=1.0,
        ),
        CleanSegment(
            segment_id=1,
            source_chunk_id=0,
            text="no change",
            original_text="no change",
            start_sec=1.0,
            end_sec=2.0,
        ),
    ]
    result = enhancer.enhance(segments)
    assert result.changed_count == 1  # Only first segment changed
