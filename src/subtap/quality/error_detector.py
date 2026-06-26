"""Error detection for aligned subtitle segments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class ErrorReport:
    """A detected error in subtitle data."""

    segment_id: int
    error_type: str  # "timeline_jump" | "too_long" | "overlap" | "bad_segmentation"
    severity: str    # "critical" | "warning" | "info"
    message: str
    stage_source: str  # "asr" | "align" | "segment"
    suggestion: str


class ErrorDetector:
    """Detects errors in aligned subtitle segments."""

    def __init__(self, aligned_path: Path):
        self.aligned_path = aligned_path

    def detect(self) -> List[ErrorReport]:
        """Detect all errors in the aligned file.

        Returns:
            List of ErrorReport for each detected issue.
        """
        if not self.aligned_path.exists():
            return []

        segments = self._load_segments()
        if not segments:
            return []

        errors: List[ErrorReport] = []
        errors.extend(self._check_too_long(segments))
        errors.extend(self._check_overlap(segments))
        errors.extend(self._check_bad_segmentation(segments))
        errors.extend(self._check_timeline_jump(segments))

        return errors

    def _load_segments(self) -> list[dict]:
        """Load aligned segments from JSONL."""
        segments = []
        for line in self.aligned_path.read_text().strip().splitlines():
            if line.strip():
                segments.append(json.loads(line))
        return segments

    def _check_too_long(self, segments: list[dict]) -> List[ErrorReport]:
        """Check for segments that are too long (>42 chars or >2 lines)."""
        errors = []
        for seg in segments:
            text = seg.get("text", "")
            # Check character count (>42 chars is warning)
            if len(text) > 42:
                errors.append(ErrorReport(
                    segment_id=seg["sentence_id"],
                    error_type="too_long",
                    severity="warning",
                    message=f"字幕过长（{len(text)}字）",
                    stage_source="segment",
                    suggestion="建议拆分为多条短字幕",
                ))
            # Check line count (>2 lines is warning)
            if text.count("\n") >= 2:
                errors.append(ErrorReport(
                    segment_id=seg["sentence_id"],
                    error_type="too_long",
                    severity="warning",
                    message=f"字幕行数过多（{text.count(chr(10)) + 1}行）",
                    stage_source="segment",
                    suggestion="建议拆分为多条短字幕",
                ))
        return errors

    def _check_overlap(self, segments: list[dict]) -> List[ErrorReport]:
        """Check for overlapping time ranges."""
        errors = []
        for i in range(len(segments) - 1):
            current = segments[i]
            next_seg = segments[i + 1]
            if current["end_sec"] > next_seg["start_sec"]:
                overlap = current["end_sec"] - next_seg["start_sec"]
                errors.append(ErrorReport(
                    segment_id=current["sentence_id"],
                    error_type="overlap",
                    severity="critical",
                    message=f"与下一条字幕重叠 {overlap:.2f}s",
                    stage_source="align",
                    suggestion="自动调整结束时间",
                ))
        return errors

    def _check_bad_segmentation(self, segments: list[dict]) -> List[ErrorReport]:
        """Check for segments without punctuation (bad segmentation)."""
        errors = []
        # Chinese punctuation characters
        punct_chars = set("，。！？、；：""''（）【】…—·")
        for seg in segments:
            text = seg.get("text", "")
            # Check if text has no punctuation and is long enough
            if len(text) >= 20 and not any(c in punct_chars for c in text):
                errors.append(ErrorReport(
                    segment_id=seg["sentence_id"],
                    error_type="bad_segmentation",
                    severity="info",
                    message="字幕无标点符号",
                    stage_source="segment",
                    suggestion="建议重跑 segment 阶段",
                ))
        return errors

    def _check_timeline_jump(self, segments: list[dict]) -> List[ErrorReport]:
        """Check for large time gaps between segments."""
        errors = []
        for i in range(len(segments) - 1):
            current = segments[i]
            next_seg = segments[i + 1]
            gap = next_seg["start_sec"] - current["end_sec"]
            if gap > 2.0:
                errors.append(ErrorReport(
                    segment_id=current["sentence_id"],
                    error_type="timeline_jump",
                    severity="warning",
                    message=f"时间轴跳跃 {gap:.2f}s",
                    stage_source="align",
                    suggestion="检查是否需要插入空字幕",
                ))
        return errors
