"""Auto-fix system for subtitle errors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from subtap.quality.error_detector import ErrorReport


@dataclass
class FixAction:
    """Record of a fix action taken."""

    segment_id: int
    fix_type: str  # "adjust_time" | "split" | "add_punct"
    description: str
    applied: bool


class Fixer:
    """Auto-fix subtitle errors based on error reports."""

    def __init__(self, aligned_path: Path):
        self.aligned_path = aligned_path

    def fix(self, errors: List[ErrorReport], output_path: Path) -> List[FixAction]:
        """Apply fixes for detected errors.

        Args:
            errors: List of ErrorReport from ErrorDetector.
            output_path: Path to write fixed aligned.jsonl.

        Returns:
            List of FixAction records.
        """
        if not self.aligned_path.exists():
            return []

        segments = self._load_segments()
        if not segments:
            return []

        actions: List[FixAction] = []

        # Group errors by segment_id for efficient processing
        errors_by_segment: dict[int, List[ErrorReport]] = {}
        for error in errors:
            if error.segment_id not in errors_by_segment:
                errors_by_segment[error.segment_id] = []
            errors_by_segment[error.segment_id].append(error)

        # Apply fixes
        for error in errors:
            if error.error_type == "overlap":
                action = self._fix_overlap(segments, error)
                if action:
                    actions.append(action)
            elif error.error_type == "too_long":
                # Too long fixes require splitting, which changes segment count
                # For now, just log it as a suggestion
                actions.append(FixAction(
                    segment_id=error.segment_id,
                    fix_type="split",
                    description=f"字幕过长，建议手动拆分: {error.message}",
                    applied=False,
                ))
            elif error.error_type == "bad_segmentation":
                actions.append(FixAction(
                    segment_id=error.segment_id,
                    fix_type="add_punct",
                    description=f"缺少标点，建议重跑 segment: {error.message}",
                    applied=False,
                ))
            elif error.error_type == "timeline_jump":
                actions.append(FixAction(
                    segment_id=error.segment_id,
                    fix_type="adjust_time",
                    description=f"时间轴跳跃: {error.message}",
                    applied=False,
                ))

        # Write fixed segments
        self._write_segments(segments, output_path)

        return actions

    def _load_segments(self) -> list[dict]:
        """Load aligned segments from JSONL."""
        segments = []
        for line in self.aligned_path.read_text().strip().splitlines():
            if line.strip():
                segments.append(json.loads(line))
        return segments

    def _write_segments(self, segments: list[dict], output_path: Path) -> None:
        """Write segments to JSONL file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for seg in segments:
                f.write(json.dumps(seg, ensure_ascii=False) + "\n")

    def _fix_overlap(self, segments: list[dict], error: ErrorReport) -> FixAction | None:
        """Fix overlapping time ranges by adjusting end_sec."""
        seg_id = error.segment_id
        # Find the segment
        for i, seg in enumerate(segments):
            if seg["sentence_id"] == seg_id and i < len(segments) - 1:
                next_seg = segments[i + 1]
                if seg["end_sec"] > next_seg["start_sec"]:
                    # Adjust end_sec to match next segment's start_sec
                    old_end = seg["end_sec"]
                    seg["end_sec"] = next_seg["start_sec"]
                    return FixAction(
                        segment_id=seg_id,
                        fix_type="adjust_time",
                        description=f"调整结束时间 {old_end:.2f}s → {seg['end_sec']:.2f}s",
                        applied=True,
                    )
        return None
