"""Tests for ASR post-processing module."""

from __future__ import annotations

import pytest

from subtap.ai.asr_postprocess import CleanEngine
from subtap.core.asr import _merge_single_letters
from subtap.schemas.models import ASRSegment


@pytest.fixture
def processor() -> CleanEngine:
    return CleanEngine()


@pytest.fixture
def sample_segments() -> list[ASRSegment]:
    return [
        ASRSegment(
            chunk_id=0,
            segment_id=0,
            text="um 今天天气很好",
            start_sec=0.0,
            end_sec=2.0,
            confidence=0.9,
        ),
        ASRSegment(
            chunk_id=1,
            segment_id=0,
            text="那个我们去公园吧",
            start_sec=2.0,
            end_sec=4.0,
            confidence=0.85,
        ),
        ASRSegment(
            chunk_id=2,
            segment_id=0,
            text="ah 你好吗",
            start_sec=4.0,
            end_sec=6.0,
            confidence=0.8,
        ),
    ]


# ── Filler Removal ──────────────────────────────────────────


class TestFillerRemoval:
    """Test filler word removal."""

    def test_removes_um(self, processor: CleanEngine, sample_segments: list):
        result = processor._remove_fillers(sample_segments)
        assert "um" not in result[0].text

    def test_removes_ah(self, processor: CleanEngine, sample_segments: list):
        result = processor._remove_fillers(sample_segments)
        assert "ah" not in result[2].text

    def test_removes_chinese_fillers(
        self, processor: CleanEngine, sample_segments: list
    ):
        result = processor._remove_fillers(sample_segments)
        assert "那个" not in result[1].text

    def test_preserves_meaning(self, processor: CleanEngine, sample_segments: list):
        result = processor._remove_fillers(sample_segments)
        assert "今天天气很好" in result[0].text
        assert "我们去公园吧" in result[1].text

    def test_handles_empty_text(self, processor: CleanEngine):
        segments = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                text="",
                start_sec=0.0,
                end_sec=1.0,
                confidence=0.5,
            )
        ]
        result = processor._remove_fillers(segments)
        assert result[0].text == ""


# ── Punctuation Restore ─────────────────────────────────────


class TestPunctuationRestore:
    """Test punctuation restoration."""

    def test_adds_period_to_statement(self, processor: CleanEngine):
        segments = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                text="今天天气很好",
                start_sec=0.0,
                end_sec=2.0,
                confidence=0.9,
            )
        ]
        result = processor._restore_punctuation(segments)
        assert result[0].text.endswith("。")

    def test_preserves_existing_punctuation(self, processor: CleanEngine):
        segments = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                text="你好吗？",
                start_sec=0.0,
                end_sec=2.0,
                confidence=0.9,
            )
        ]
        result = processor._restore_punctuation(segments)
        assert result[0].text.endswith("？")

    def test_handles_question_mark(self, processor: CleanEngine):
        segments = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                text="你是谁",
                start_sec=0.0,
                end_sec=2.0,
                confidence=0.9,
            )
        ]
        result = processor._restore_punctuation(segments)
        # Should detect question context
        assert result[0].text[-1] in "？。！"


# ── Entity Normalization ─────────────────────────────────────


class TestEntityNormalization:
    """Test entity normalization."""

    def test_normalizes_case(self, processor: CleanEngine):
        segments = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                text="gpt is good",
                start_sec=0.0,
                end_sec=2.0,
                confidence=0.9,
            )
        ]
        result = processor._normalize_entities(segments, glossary_terms={"gpt": "GPT"})
        assert "GPT" in result[0].text

    def test_applies_glossary(self, processor: CleanEngine):
        segments = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                text="机器学习很有趣",
                start_sec=0.0,
                end_sec=2.0,
                confidence=0.9,
            )
        ]
        result = processor._normalize_entities(
            segments, glossary_terms={"机器学习": "ML"}
        )
        assert "ML" in result[0].text

    def test_handles_no_glossary(self, processor: CleanEngine):
        segments = [
            ASRSegment(
                chunk_id=0,
                segment_id=0,
                text="今天天气好",
                start_sec=0.0,
                end_sec=2.0,
                confidence=0.9,
            )
        ]
        result = processor._normalize_entities(segments)
        assert result[0].text == "今天天气好"


# ── Full Pipeline ────────────────────────────────────────────


class TestFullPipeline:
    """Test full ASR post-processing pipeline."""

    def test_process_returns_segments(
        self, processor: CleanEngine, sample_segments: list
    ):
        result = processor.process(sample_segments)
        assert len(result) == len(sample_segments)

    def test_process_removes_fillers(
        self, processor: CleanEngine, sample_segments: list
    ):
        result = processor.process(sample_segments)
        for seg in result:
            assert "um" not in seg.text
            assert "ah" not in seg.text
            assert "那个" not in seg.text

    def test_process_returns_asr_segments(
        self, processor: CleanEngine, sample_segments: list
    ):
        result = processor.process(sample_segments)
        assert all(isinstance(s, ASRSegment) for s in result)


def test_merge_single_letters():
    """连续单字母应合并为一个词。"""
    words = [
        {"word": "U", "start_sec": 0.0, "end_sec": 0.1},
        {"word": "F", "start_sec": 0.1, "end_sec": 0.2},
        {"word": "S", "start_sec": 0.2, "end_sec": 0.3},
        {"word": "格", "start_sec": 0.5, "end_sec": 0.7},
    ]
    result = _merge_single_letters(words)
    assert len(result) == 2
    assert result[0]["word"] == "UFS"
    assert result[0]["start_sec"] == 0.0
    assert result[0]["end_sec"] == 0.3


def test_merge_single_letters_mixed():
    """单字母与正常词混合时只合并连续单字母。"""
    words = [
        {"word": "点", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "击", "start_sec": 0.2, "end_sec": 0.4},
        {"word": "V", "start_sec": 0.5, "end_sec": 0.6},
        {"word": "o", "start_sec": 0.6, "end_sec": 0.7},
        {"word": "i", "start_sec": 0.7, "end_sec": 0.8},
        {"word": "c", "start_sec": 0.8, "end_sec": 0.9},
        {"word": "e", "start_sec": 0.9, "end_sec": 1.0},
        {"word": "I", "start_sec": 1.0, "end_sec": 1.1},
        {"word": "S", "start_sec": 1.1, "end_sec": 1.2},
        {"word": "O", "start_sec": 1.2, "end_sec": 1.3},
    ]
    result = _merge_single_letters(words)
    assert result[1]["word"] == "VoiceISO"


def test_no_merge_for_normal_words():
    """正常词不合并。"""
    words = [
        {"word": "你好", "start_sec": 0.0, "end_sec": 0.2},
        {"word": "世界", "start_sec": 0.3, "end_sec": 0.5},
    ]
    result = _merge_single_letters(words)
    assert len(result) == 2


def test_empty_words():
    """空列表返回空。"""
    assert _merge_single_letters([]) == []
