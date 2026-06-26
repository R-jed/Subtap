"""Tests for align refiner module."""

from __future__ import annotations

import pytest

from subtap.ai.align_refiner import AlignEngine
from subtap.schemas.models import AlignedSegment


@pytest.fixture
def refiner() -> AlignEngine:
    return AlignEngine()


@pytest.fixture
def overlapping_segments() -> list[AlignedSegment]:
    return [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.5, text="第一句。"),
        AlignedSegment(sentence_id=1, start_sec=2.3, end_sec=4.0, text="第二句。"),  # Overlaps
        AlignedSegment(sentence_id=2, start_sec=4.0, end_sec=6.0, text="第三句。"),
    ]


@pytest.fixture
def normal_segments() -> list[AlignedSegment]:
    return [
        AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.0, text="第一句。"),
        AlignedSegment(sentence_id=1, start_sec=2.0, end_sec=4.0, text="第二句。"),
        AlignedSegment(sentence_id=2, start_sec=4.0, end_sec=6.0, text="第三句。"),
    ]


# ── Smooth Timing ────────────────────────────────────────────


class TestSmoothTiming:
    """Test timing smoothing."""

    def test_smooths_small_jumps(self, refiner: AlignEngine):
        segments = [
            AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.0, text="第一句。"),
            AlignedSegment(sentence_id=1, start_sec=2.5, end_sec=4.0, text="第二句。"),  # 0.5s gap
        ]
        result = refiner._smooth_timing(segments)
        # Should not change much (gap within tolerance)
        assert result[1].start_sec >= 2.0

    def test_preserves_normal_timing(self, refiner: AlignEngine, normal_segments: list):
        result = refiner._smooth_timing(normal_segments)
        assert result[0].start_sec == 0.0
        assert result[0].end_sec == 2.0


# ── Fix Overlaps ─────────────────────────────────────────────


class TestFixOverlaps:
    """Test overlap correction."""

    def test_fixes_overlap(self, refiner: AlignEngine, overlapping_segments: list):
        result = refiner._fix_overlaps(overlapping_segments)
        for i in range(len(result) - 1):
            assert result[i].end_sec <= result[i + 1].start_sec

    def test_preserves_non_overlapping(self, refiner: AlignEngine, normal_segments: list):
        result = refiner._fix_overlaps(normal_segments)
        assert result[0].end_sec == 2.0
        assert result[1].start_sec == 2.0

    def test_fixes_multiple_overlaps(self, refiner: AlignEngine):
        segments = [
            AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=3.0, text="第一句。"),
            AlignedSegment(sentence_id=1, start_sec=2.0, end_sec=5.0, text="第二句。"),
            AlignedSegment(sentence_id=2, start_sec=4.0, end_sec=7.0, text="第三句。"),
        ]
        result = refiner._fix_overlaps(segments)
        for i in range(len(result) - 1):
            assert result[i].end_sec <= result[i + 1].start_sec


# ── Snap to Silence ──────────────────────────────────────────


class TestSnapToSilence:
    """Test silence boundary snapping."""

    def test_snaps_to_boundary(self, refiner: AlignEngine):
        segments = [
            AlignedSegment(sentence_id=0, start_sec=0.0, end_sec=2.1, text="第一句。"),
            AlignedSegment(sentence_id=1, start_sec=2.1, end_sec=4.0, text="第二句。"),
        ]
        result = refiner._snap_to_silence(segments)
        # Should snap to nearest silence boundary
        assert result[0].end_sec <= 2.1

    def test_preserves_reasonable_timing(self, refiner: AlignEngine, normal_segments: list):
        result = refiner._snap_to_silence(normal_segments)
        assert result[0].end_sec == 2.0


# ── Full Pipeline ────────────────────────────────────────────


class TestRefinerPipeline:
    """Test full refinement pipeline."""

    def test_refine_returns_aligned_segments(self, refiner: AlignEngine, overlapping_segments: list):
        result = refiner.refine(overlapping_segments)
        assert all(isinstance(s, AlignedSegment) for s in result)

    def test_refine_fixes_overlaps(self, refiner: AlignEngine, overlapping_segments: list):
        result = refiner.refine(overlapping_segments)
        for i in range(len(result) - 1):
            assert result[i].end_sec <= result[i + 1].start_sec

    def test_refine_preserves_count(self, refiner: AlignEngine, overlapping_segments: list):
        result = refiner.refine(overlapping_segments)
        assert len(result) == len(overlapping_segments)

    def test_refine_no_time_regression(self, refiner: AlignEngine, overlapping_segments: list):
        result = refiner.refine(overlapping_segments)
        for seg in result:
            assert seg.end_sec >= seg.start_sec
