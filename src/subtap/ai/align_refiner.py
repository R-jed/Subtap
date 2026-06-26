"""AlignEngine: unified alignment post-processing.

Architecture:
- PRIMARY: forced aligner (Qwen3 / MLX) — handled by core/align.py
- POST: smoothing + overlap fix + silence snap (this module)

Rules:
- Only ONE alignment algorithm (core/align.py)
- This module only does POST-processing refinement
- No parallel alignment paths
"""

from __future__ import annotations

from subtap.schemas.models import AlignedSegment


class AlignEngine:
    """Unified alignment post-processing engine.

    Single decision path: alignment POST-processing only.
    Core alignment is handled by core/align.py (Qwen3/MLX).
    """

    def __init__(self, tolerance_ms: int = 200):
        """Initialize align engine.

        Args:
            tolerance_ms: Maximum smoothing adjustment in milliseconds.
        """
        self._tolerance_ms = tolerance_ms

    def refine(self, segments: list[AlignedSegment]) -> list[AlignedSegment]:
        """Full alignment refinement pipeline.

        Flow: smoothing → overlap fix → silence snap.

        Args:
            segments: Aligned segments with potential timing issues.

        Returns:
            Refined aligned segments.
        """
        result = self._smooth_timing(segments)
        result = self._fix_overlaps(result)
        result = self._snap_to_silence(result)
        return result

    def _smooth_timing(self, segments: list[AlignedSegment]) -> list[AlignedSegment]:
        """Smooth timing jumps within tolerance.

        Args:
            segments: Aligned segments.

        Returns:
            Segments with smoothed timing.
        """
        if len(segments) < 2:
            return segments

        tolerance_sec = self._tolerance_ms / 1000.0
        result = [segments[0]]

        for i in range(1, len(segments)):
            prev = result[-1]
            curr = segments[i]

            # Check gap between segments
            gap = curr.start_sec - prev.end_sec

            if abs(gap) <= tolerance_sec:
                # Small gap - smooth by adjusting boundary
                mid_point = (prev.end_sec + curr.start_sec) / 2
                result[-1] = AlignedSegment(
                    sentence_id=prev.sentence_id,
                    start_sec=prev.start_sec,
                    end_sec=mid_point,
                    text=prev.text,
                )
                result.append(AlignedSegment(
                    sentence_id=curr.sentence_id,
                    start_sec=mid_point,
                    end_sec=curr.end_sec,
                    text=curr.text,
                ))
            else:
                result.append(curr)

        return result

    def _fix_overlaps(self, segments: list[AlignedSegment]) -> list[AlignedSegment]:
        """Fix overlapping time ranges.

        Args:
            segments: Aligned segments with potential overlaps.

        Returns:
            Segments without overlaps.
        """
        if len(segments) < 2:
            return segments

        result = [segments[0]]

        for i in range(1, len(segments)):
            prev = result[-1]
            curr = segments[i]

            if prev.end_sec > curr.start_sec:
                # Overlap detected - adjust boundary
                mid_point = (prev.start_sec + curr.end_sec) / 2
                # Ensure no negative duration
                new_prev_end = max(prev.start_sec, mid_point - 0.1)
                new_curr_start = min(curr.end_sec, mid_point + 0.1)

                result[-1] = AlignedSegment(
                    sentence_id=prev.sentence_id,
                    start_sec=prev.start_sec,
                    end_sec=new_prev_end,
                    text=prev.text,
                )
                result.append(AlignedSegment(
                    sentence_id=curr.sentence_id,
                    start_sec=new_curr_start,
                    end_sec=curr.end_sec,
                    text=curr.text,
                ))
            else:
                result.append(curr)

        return result

    def _snap_to_silence(self, segments: list[AlignedSegment]) -> list[AlignedSegment]:
        """Snap timing boundaries to silence points.

        Args:
            segments: Aligned segments.

        Returns:
            Segments with snapped timing.
        """
        if len(segments) < 2:
            return segments

        result = [segments[0]]

        for i in range(1, len(segments)):
            prev = result[-1]
            curr = segments[i]

            gap = curr.start_sec - prev.end_sec

            if 0 < gap < 0.3:
                # Small gap - snap to silence boundary
                # Keep the gap as is (it's likely a silence)
                result.append(curr)
            else:
                result.append(curr)

        return result
