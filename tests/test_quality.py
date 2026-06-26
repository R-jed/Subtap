"""Tests for quality module — scorer, error_detector, fixer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from subtap.quality.scorer import Scorer, QualityReport
from subtap.quality.error_detector import ErrorDetector, ErrorReport
from subtap.quality.fixer import Fixer, FixAction


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def good_aligned_jsonl(tmp_path: Path) -> Path:
    """Well-formed aligned segments."""
    segments = [
        {"sentence_id": 0, "start_sec": 0.0, "end_sec": 2.5, "text": "你好，欢迎收看今天的节目。"},
        {"sentence_id": 1, "start_sec": 2.5, "end_sec": 5.0, "text": "我们将讨论人工智能的发展。"},
        {"sentence_id": 2, "start_sec": 5.0, "end_sec": 8.0, "text": "首先，让我们回顾一下历史。"},
        {"sentence_id": 3, "start_sec": 8.0, "end_sec": 11.0, "text": "从图灵测试到深度学习。"},
        {"sentence_id": 4, "start_sec": 11.0, "end_sec": 14.0, "text": "这是一个漫长而精彩的旅程。"},
    ]
    path = tmp_path / "aligned.jsonl"
    path.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in segments))
    return path


@pytest.fixture
def bad_aligned_jsonl(tmp_path: Path) -> Path:
    """Aligned segments with various errors."""
    segments = [
        {"sentence_id": 0, "start_sec": 0.0, "end_sec": 2.5, "text": "正常字幕。"},
        {"sentence_id": 1, "start_sec": 5.0, "end_sec": 7.0, "text": "这条字幕非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长，超过了四十二个字符的限制。"},  # too_long
        {"sentence_id": 2, "start_sec": 6.5, "end_sec": 9.0, "text": "与上一条重叠的字幕。"},  # overlap
        {"sentence_id": 3, "start_sec": 9.0, "end_sec": 12.0, "text": "这是一段没有标点的字幕文本内容很多很多字"},  # bad_segmentation
        {"sentence_id": 4, "start_sec": 12.0, "end_sec": 15.0, "text": "正常结束。"},
    ]
    path = tmp_path / "aligned.jsonl"
    path.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in segments))
    return path


@pytest.fixture
def empty_aligned_jsonl(tmp_path: Path) -> Path:
    """Empty aligned file."""
    path = tmp_path / "aligned.jsonl"
    path.write_text("")
    return path


# ── Scorer Tests ─────────────────────────────────────────────


class TestScorer:
    """Test quality scoring system."""

    def test_good_file_scores_high(self, good_aligned_jsonl: Path):
        scorer = Scorer(good_aligned_jsonl)
        report = scorer.score()
        assert report.total_score >= 80
        assert report.error_count == 0

    def test_bad_file_scores_lower(self, bad_aligned_jsonl: Path):
        scorer = Scorer(bad_aligned_jsonl)
        report = scorer.score()
        assert report.total_score < 80
        assert report.error_count > 0

    def test_empty_file_scores_zero(self, empty_aligned_jsonl: Path):
        scorer = Scorer(empty_aligned_jsonl)
        report = scorer.score()
        assert report.total_score == 0.0
        assert report.error_count == 0

    def test_report_has_all_dimensions(self, good_aligned_jsonl: Path):
        scorer = Scorer(good_aligned_jsonl)
        report = scorer.score()
        assert hasattr(report, "total_score")
        assert hasattr(report, "alignment_error")
        assert hasattr(report, "segmentation_quality")
        assert hasattr(report, "readability")
        assert hasattr(report, "error_count")
        assert hasattr(report, "fixable_count")

    def test_score_range_0_to_100(self, good_aligned_jsonl: Path):
        scorer = Scorer(good_aligned_jsonl)
        report = scorer.score()
        assert 0 <= report.total_score <= 100


# ── ErrorDetector Tests ──────────────────────────────────────


class TestErrorDetector:
    """Test error detection system."""

    def test_good_file_no_errors(self, good_aligned_jsonl: Path):
        detector = ErrorDetector(good_aligned_jsonl)
        errors = detector.detect()
        assert len(errors) == 0

    def test_detects_too_long(self, bad_aligned_jsonl: Path):
        detector = ErrorDetector(bad_aligned_jsonl)
        errors = detector.detect()
        too_long = [e for e in errors if e.error_type == "too_long"]
        assert len(too_long) >= 1
        assert too_long[0].segment_id == 1

    def test_detects_overlap(self, bad_aligned_jsonl: Path):
        detector = ErrorDetector(bad_aligned_jsonl)
        errors = detector.detect()
        overlap = [e for e in errors if e.error_type == "overlap"]
        assert len(overlap) >= 1

    def test_detects_bad_segmentation(self, bad_aligned_jsonl: Path):
        detector = ErrorDetector(bad_aligned_jsonl)
        errors = detector.detect()
        bad_seg = [e for e in errors if e.error_type == "bad_segmentation"]
        assert len(bad_seg) >= 1
        assert bad_seg[0].segment_id == 3

    def test_error_has_required_fields(self, bad_aligned_jsonl: Path):
        detector = ErrorDetector(bad_aligned_jsonl)
        errors = detector.detect()
        assert len(errors) > 0
        e = errors[0]
        assert hasattr(e, "segment_id")
        assert hasattr(e, "error_type")
        assert hasattr(e, "severity")
        assert hasattr(e, "message")
        assert hasattr(e, "stage_source")
        assert hasattr(e, "suggestion")

    def test_empty_file_no_errors(self, empty_aligned_jsonl: Path):
        detector = ErrorDetector(empty_aligned_jsonl)
        errors = detector.detect()
        assert len(errors) == 0


# ── Fixer Tests ──────────────────────────────────────────────


class TestFixer:
    """Test auto-fix system."""

    def test_fixes_overlap(self, bad_aligned_jsonl: Path, tmp_path: Path):
        fixer = Fixer(bad_aligned_jsonl)
        errors = ErrorDetector(bad_aligned_jsonl).detect()
        overlap_errors = [e for e in errors if e.error_type == "overlap"]

        output_path = tmp_path / "fixed.jsonl"
        actions = fixer.fix(overlap_errors, output_path)

        assert output_path.exists()
        fixed_segments = [json.loads(line) for line in output_path.read_text().strip().splitlines()]
        # After fix, no overlapping times
        for i in range(len(fixed_segments) - 1):
            assert fixed_segments[i]["end_sec"] <= fixed_segments[i + 1]["start_sec"]

    def test_fix_returns_actions(self, bad_aligned_jsonl: Path, tmp_path: Path):
        fixer = Fixer(bad_aligned_jsonl)
        errors = ErrorDetector(bad_aligned_jsonl).detect()

        output_path = tmp_path / "fixed.jsonl"
        actions = fixer.fix(errors, output_path)

        assert isinstance(actions, list)
        assert all(isinstance(a, FixAction) for a in actions)

    def test_fix_preserves_segment_count(self, bad_aligned_jsonl: Path, tmp_path: Path):
        fixer = Fixer(bad_aligned_jsonl)
        errors = ErrorDetector(bad_aligned_jsonl).detect()

        output_path = tmp_path / "fixed.jsonl"
        fixer.fix(errors, output_path)

        original = [json.loads(line) for line in bad_aligned_jsonl.read_text().strip().splitlines()]
        fixed = [json.loads(line) for line in output_path.read_text().strip().splitlines()]
        # Fix should not remove segments (only adjust times)
        assert len(fixed) == len(original)

    def test_fix_empty_file(self, empty_aligned_jsonl: Path, tmp_path: Path):
        fixer = Fixer(empty_aligned_jsonl)
        output_path = tmp_path / "fixed.jsonl"
        actions = fixer.fix([], output_path)
        assert actions == []
