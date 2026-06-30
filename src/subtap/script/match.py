"""Script matching: format → align → correct."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from subtap.script.formatter import format_script
from subtap.script.loader import load_script
from subtap.script.aligner import (
    align_sequences,
    compute_alignment_quality,
    AlignmentQualityError,
)
from subtap.script.corrector import correct_segments


@dataclass
class MatchReport:
    """User-facing match report."""

    matched: int = 0
    corrected: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)
    message: str = ""


def match_script_lines(
    segments: list[dict],
    script_text: str,
    mode: str = "follow_script",
) -> tuple[list[dict], MatchReport]:
    """Main entry: format → align → correct.

    Args:
        segments: ASR segments (list of dicts with text, start_sec, end_sec).
        script_text: Raw script text (already loaded).
        mode: "follow_script" or "correct_only".

    Returns:
        Tuple of (corrected segments, report).
    """
    if mode not in {"follow_script", "correct_only"}:
        raise ValueError(f"未知文稿匹配模式：{mode}")

    # Step 1: Format script
    ref_lines = format_script(script_text)

    if not ref_lines:
        return [], MatchReport(
            message="文稿内容为空",
            warnings=["文稿内容为空，请检查文稿文件"],
        )

    if not segments:
        return [], MatchReport(
            message="无转录内容",
            warnings=["无转录内容"],
        )

    # Step 2: Align
    try:
        ops = align_sequences(
            [s["text"] for s in segments],
            ref_lines,
        )
        compute_alignment_quality(ops, [s["text"] for s in segments], ref_lines)
    except AlignmentQualityError as e:
        return list(segments), MatchReport(
            message=str(e),
            warnings=[str(e)],
        )

    # Step 3: Correct
    result, skipped = correct_segments(segments, ops, ref_lines)

    # Build report
    matched = sum(1 for op in ops if op.op in ("equal", "replace"))
    corrected = sum(1 for op in ops if op.op == "replace")
    asr_extra = sum(1 for op in ops if op.op == "delete")
    script_extra = sum(1 for op in ops if op.op == "insert")

    warnings = []
    if skipped > 0:
        warnings.append(f"{skipped} 句匹配度较低，已保留原转录")
    if asr_extra > 0:
        warnings.append(f"有 {asr_extra} 句未匹配到文稿，已保留原转录")
    if script_extra > 0:
        warnings.append(f"文稿中有 {script_extra} 句未在音频中找到，已跳过")

    message = f"文稿匹配完成，已纠错 {corrected} 句"

    return result, MatchReport(
        matched=matched,
        corrected=corrected,
        skipped=skipped,
        warnings=warnings,
        message=message,
    )


def match_from_file(
    segments: list[dict],
    script_path: Path,
    mode: str = "follow_script",
) -> tuple[list[dict], MatchReport]:
    """Convenience: load script file and match.

    Args:
        segments: ASR segments.
        script_path: Path to script file.
        mode: "follow_script" or "correct_only".

    Returns:
        Tuple of (corrected segments, report).
    """
    script_text = load_script(script_path)
    return match_script_lines(segments, script_text, mode=mode)
