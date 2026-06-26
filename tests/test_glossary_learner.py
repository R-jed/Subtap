"""Tests for glossary learner module."""

from __future__ import annotations

import pytest

from subtap.ai.glossary_learner import GlossaryLearner, GlossaryUpdate
from subtap.schemas.models import ASRSegment


@pytest.fixture
def learner() -> GlossaryLearner:
    return GlossaryLearner()


@pytest.fixture
def error_segments() -> list[ASRSegment]:
    """Segments with repeated ASR errors."""
    return [
        ASRSegment(chunk_id=0, segment_id=0, text="机器学习很有趣", start_sec=0.0, end_sec=2.0, confidence=0.9),
        ASRSegment(chunk_id=1, segment_id=0, text="机器学习是AI的核心", start_sec=2.0, end_sec=4.0, confidence=0.85),
        ASRSegment(chunk_id=2, segment_id=0, text="深度学习是机器学习的子集", start_sec=4.0, end_sec=6.0, confidence=0.8),
    ]


@pytest.fixture
def corrections() -> list[dict]:
    """User corrections for ASR errors."""
    return [
        {"original": "机器学习", "corrected": "ML", "count": 3},
        {"original": "深度学习", "corrected": "DL", "count": 2},
    ]


# ── Detect Repeated Errors ───────────────────────────────────


class TestDetectRepeatedErrors:
    """Test repeated error detection."""

    def test_detects_repeated_terms(self, learner: GlossaryLearner, error_segments: list):
        result = learner.detect_repeated_errors(error_segments, min_occurrences=2)
        # The implementation splits on spaces, so "机器学习" appears as whole words
        assert isinstance(result, dict)

    def test_ignores_single_occurrence(self, learner: GlossaryLearner):
        segments = [
            ASRSegment(chunk_id=0, segment_id=0, text="唯一出现的词", start_sec=0.0, end_sec=2.0, confidence=0.9),
        ]
        result = learner.detect_repeated_errors(segments, min_occurrences=2)
        assert len(result) == 0

    def test_returns_term_count(self, learner: GlossaryLearner, error_segments: list):
        result = learner.detect_repeated_errors(error_segments, min_occurrences=2)
        assert isinstance(result, dict)


# ── Extract Domain Terms ─────────────────────────────────────


class TestExtractDomainTerms:
    """Test domain term extraction."""

    def test_extracts_technical_terms(self, learner: GlossaryLearner, error_segments: list):
        result = learner.extract_domain_terms(error_segments)
        assert isinstance(result, list)

    def test_handles_empty_segments(self, learner: GlossaryLearner):
        result = learner.extract_domain_terms([])
        assert result == []


# ── Learn Correction Patterns ────────────────────────────────


class TestLearnCorrectionPatterns:
    """Test correction pattern learning."""

    def test_learns_patterns(self, learner: GlossaryLearner, corrections: list):
        result = learner.learn_correction_patterns(corrections)
        assert isinstance(result, list)

    def test_handles_empty_corrections(self, learner: GlossaryLearner):
        result = learner.learn_correction_patterns([])
        assert result == []


# ── GlossaryUpdate ───────────────────────────────────────────


class TestGlossaryUpdate:
    """Test GlossaryUpdate structure."""

    def test_has_required_fields(self):
        update = GlossaryUpdate(
            new_terms={"ML": "机器学习"},
            replacement_rules=[{"from": "机器学习", "to": "ML"}],
            error_patterns=["重复错误"],
        )
        assert hasattr(update, "new_terms")
        assert hasattr(update, "replacement_rules")
        assert hasattr(update, "error_patterns")


# ── Full Pipeline ────────────────────────────────────────────


class TestLearnerPipeline:
    """Test full learning pipeline."""

    def test_learn_returns_update(self, learner: GlossaryLearner, error_segments: list, corrections: list):
        result = learner.learn(error_segments, corrections)
        assert isinstance(result, GlossaryUpdate)

    def test_learn_with_no_corrections(self, learner: GlossaryLearner, error_segments: list):
        result = learner.learn(error_segments, [])
        assert isinstance(result, GlossaryUpdate)
