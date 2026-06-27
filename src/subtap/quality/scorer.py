"""Quality scoring system for aligned subtitle segments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from subtap.quality.error_detector import ErrorDetector


@dataclass
class QualityReport:
    """Quality assessment report for subtitle data."""

    total_score: float  # 0-100 总分
    alignment_error: float  # 对齐误差得分
    segmentation_quality: float  # 断句质量得分
    readability: float  # 可读性得分
    error_count: int
    fixable_count: int


class Scorer:
    """Scores subtitle quality based on aligned segments."""

    def __init__(self, aligned_path: Path):
        self.aligned_path = aligned_path

    def score(self) -> QualityReport:
        """Calculate quality score for the aligned file.

        Returns:
            QualityReport with scores and error counts.
        """
        if not self.aligned_path.exists():
            return QualityReport(
                total_score=0.0,
                alignment_error=0.0,
                segmentation_quality=0.0,
                readability=0.0,
                error_count=0,
                fixable_count=0,
            )

        segments = self._load_segments()
        if not segments:
            return QualityReport(
                total_score=0.0,
                alignment_error=0.0,
                segmentation_quality=0.0,
                readability=0.0,
                error_count=0,
                fixable_count=0,
            )

        # Detect errors
        detector = ErrorDetector(self.aligned_path)
        errors = detector.detect()
        error_count = len(errors)
        fixable_count = sum(
            1 for e in errors if e.error_type in ("overlap", "too_long")
        )

        # Calculate dimension scores
        alignment_score = self._score_alignment(segments, errors)
        segmentation_score = self._score_segmentation(segments, errors)
        readability_score = self._score_readability(segments, errors)

        # Weighted total: alignment 40%, segmentation 30%, readability 30%
        total = (
            alignment_score * 0.4 + segmentation_score * 0.3 + readability_score * 0.3
        )

        return QualityReport(
            total_score=round(total, 1),
            alignment_error=round(alignment_score, 1),
            segmentation_quality=round(segmentation_score, 1),
            readability=round(readability_score, 1),
            error_count=error_count,
            fixable_count=fixable_count,
        )

    def _load_segments(self) -> list[dict]:
        """Load aligned segments from JSONL."""
        segments = []
        for line in self.aligned_path.read_text().strip().splitlines():
            if line.strip():
                segments.append(json.loads(line))
        return segments

    def _score_alignment(self, segments: list[dict], errors: list) -> float:
        """Score alignment quality (0-100)."""
        if not segments:
            return 0.0

        # Start with 100, deduct for alignment errors
        score = 100.0
        for error in errors:
            if error.error_type == "overlap":
                score -= 30.0  # Critical: overlaps
            elif error.error_type == "timeline_jump":
                score -= 5.0  # Warning: gaps

        return max(0.0, score)

    def _score_segmentation(self, segments: list[dict], errors: list) -> float:
        """Score segmentation quality (0-100)."""
        if not segments:
            return 0.0

        score = 100.0
        for error in errors:
            if error.error_type == "bad_segmentation":
                score -= 15.0  # Info: no punctuation
            elif error.error_type == "too_long":
                score -= 8.0  # Warning: too long

        return max(0.0, score)

    def _score_readability(self, segments: list[dict], errors: list) -> float:
        """Score readability (0-100)."""
        if not segments:
            return 0.0

        score = 100.0
        for error in errors:
            if error.error_type == "too_long":
                score -= 10.0  # Long text hurts readability

        # Check average segment length
        avg_len = sum(len(s.get("text", "")) for s in segments) / len(segments)
        if avg_len > 30:
            score -= 5.0  # Long average hurts readability

        return max(0.0, score)
