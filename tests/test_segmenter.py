"""Tests for smart segmenter module."""

from __future__ import annotations

import pytest

from subtap.ai.segmenter import SentenceEngine
from subtap.schemas.models import SentenceSegment


@pytest.fixture
def segmenter() -> SentenceEngine:
    return SentenceEngine(use_spacy=False)


@pytest.fixture
def long_texts() -> list[str]:
    return ["今天天气很好我们一起去公园散步吧那里有很多人在锻炼身体"]


@pytest.fixture
def long_timings() -> list[tuple[float, float]]:
    return [(0.0, 8.0)]


@pytest.fixture
def normal_texts() -> list[str]:
    return ["今天天气很好。", "我们去公园吧。"]


@pytest.fixture
def normal_timings() -> list[tuple[float, float]]:
    return [(0.0, 2.0), (2.0, 4.0)]


# ── Rule-based Split ────────────────────────────────────────


class TestRuleBasedSplit:
    """Test rule-based splitting."""

    def test_splits_on_period(self, segmenter: SentenceEngine):
        texts = ["今天天气很好。我们去公园吧。"]
        timings = [(0.0, 4.0)]
        result = segmenter._rule_based_split(texts, timings, [0])
        assert len(result) >= 2

    def test_splits_on_question_mark(self, segmenter: SentenceEngine):
        texts = ["你是谁？我是小明。"]
        timings = [(0.0, 4.0)]
        result = segmenter._rule_based_split(texts, timings, [0])
        assert len(result) >= 2

    def test_preserves_short_text(self, segmenter: SentenceEngine):
        texts = ["你好。"]
        timings = [(0.0, 2.0)]
        result = segmenter._rule_based_split(texts, timings, [0])
        assert len(result) >= 1


# ── Length Balance ───────────────────────────────────────────


class TestLengthBalance:
    """Test length balancing."""

    def test_splits_long_sentence(self, segmenter: SentenceEngine):
        segments = [
            SentenceSegment(
                sentence_id=0,
                chunk_id=0,
                text="今天天气很好我们一起去公园散步吧那里有很多人在锻炼身体",
                start_sec=0.0,
                end_sec=8.0,
                source_text="今天天气很好我们一起去公园散步吧那里有很多人在锻炼身体",
            )
        ]
        result = segmenter._balance_length(segments)
        for seg in result:
            assert len(seg.text) <= 42

    def test_preserves_short_sentence(self, segmenter: SentenceEngine):
        segments = [
            SentenceSegment(
                sentence_id=0,
                chunk_id=0,
                text="你好。",
                start_sec=0.0,
                end_sec=2.0,
                source_text="你好。",
            )
        ]
        result = segmenter._balance_length(segments)
        assert len(result) >= 1

    def test_preserves_time_order(
        self, segmenter: SentenceEngine, long_texts, long_timings
    ):
        sentences = segmenter._rule_based_split(long_texts, long_timings, [0])
        result = segmenter._balance_length(sentences)
        for i in range(len(result) - 1):
            assert result[i].end_sec <= result[i + 1].start_sec


# ── CPS Control ─────────────────────────────────────────────


class TestCPSControl:
    """Test characters per second control."""

    def test_adjusts_high_cps(self, segmenter: SentenceEngine):
        segments = [
            SentenceSegment(
                sentence_id=0,
                chunk_id=0,
                text="今天天气很好我们一起去公园吧那里有很多人在锻炼身体",
                start_sec=0.0,
                end_sec=1.0,  # Very short time = high CPS (24 chars / 1s = 24 CPS)
                source_text="今天天气很好我们一起去公园吧那里有很多人在锻炼身体",
            )
        ]
        result = segmenter._limit_cps(segments)
        # Should extend time to meet CPS constraint (24 chars / 15 CPS = 1.6s)
        assert result[0].end_sec > 1.0

    def test_preserves_normal_cps(self, segmenter: SentenceEngine):
        segments = [
            SentenceSegment(
                sentence_id=0,
                chunk_id=0,
                text="你好。",
                start_sec=0.0,
                end_sec=2.0,
                source_text="你好。",
            )
        ]
        result = segmenter._limit_cps(segments)
        assert result[0].end_sec == 2.0

    def test_segment_returns_sentence_segments(
        self, segmenter: SentenceEngine, normal_texts, normal_timings
    ):
        result = segmenter.segment(normal_texts, normal_timings)
        assert all(isinstance(s, SentenceSegment) for s in result)

    def test_segment_preserves_content(
        self, segmenter: SentenceEngine, normal_texts, normal_timings
    ):
        result = segmenter.segment(normal_texts, normal_timings)
        combined = "".join(s.text for s in result)
        assert "今天天气" in combined
        assert "公园" in combined

    def test_segment_respects_length_limit(
        self, segmenter: SentenceEngine, long_texts, long_timings
    ):
        result = segmenter.segment(long_texts, long_timings)
        for seg in result:
            assert len(seg.text) <= 42


# ── Full Pipeline ────────────────────────────────────────────


class TestSegmenterPipeline:
    """Test full segmentation pipeline."""

    def test_segment_returns_sentence_segments(
        self, segmenter: SentenceEngine, normal_texts, normal_timings
    ):
        result = segmenter.segment(normal_texts, normal_timings)
        assert all(isinstance(s, SentenceSegment) for s in result)

    def test_segment_preserves_content(
        self, segmenter: SentenceEngine, normal_texts, normal_timings
    ):
        result = segmenter.segment(normal_texts, normal_timings)
        combined = "".join(s.text for s in result)
        assert "今天天气" in combined
        assert "公园" in combined

    def test_segment_respects_length_limit(
        self, segmenter: SentenceEngine, long_texts, long_timings
    ):
        result = segmenter.segment(long_texts, long_timings)
        for seg in result:
            assert len(seg.text) <= 42
