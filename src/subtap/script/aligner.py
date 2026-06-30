"""Sequence alignment using difflib."""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from rapidfuzz.fuzz import ratio as fuzz_ratio

ALIGNMENT_QUALITY_THRESHOLD = 0.3
CORRECTION_THRESHOLD = 0.7


@dataclass
class AlignOp:
    """A single alignment operation."""

    op: str  # "equal" | "replace" | "insert" | "delete"
    asr_idx: int | None
    ref_idx: int | None


class AlignmentQualityError(Exception):
    """Raised when alignment quality is too low."""


def align_sequences(
    asr_lines: list[str],
    ref_lines: list[str],
) -> list[AlignOp]:
    """Align ASR lines with reference lines using sequential matching.

    Args:
        asr_lines: ASR output lines.
        ref_lines: Formatted reference manuscript lines.

    Returns:
        List of alignment operations.
    """
    sm = difflib.SequenceMatcher(None, asr_lines, ref_lines)
    ops = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                ops.append(AlignOp("equal", i1 + k, j1 + k))
        elif tag == "replace":
            for k in range(max(i2 - i1, j2 - j1)):
                asr_i = i1 + k if k < (i2 - i1) else None
                ref_j = j1 + k if k < (j2 - j1) else None
                ops.append(AlignOp("replace", asr_i, ref_j))
        elif tag == "insert":
            for k in range(j2 - j1):
                ops.append(AlignOp("insert", None, j1 + k))
        elif tag == "delete":
            for k in range(i2 - i1):
                ops.append(AlignOp("delete", i1 + k, None))
    return ops


def compute_alignment_quality(
    ops: list[AlignOp],
    asr_lines: list[str],
    ref_lines: list[str],
) -> float:
    """Compute alignment quality score.

    Args:
        ops: Alignment operations.
        asr_lines: ASR output lines.
        ref_lines: Reference manuscript lines.

    Returns:
        Quality score 0.0 ~ 1.0.

    Raises:
        AlignmentQualityError: If quality is below threshold.
    """
    replace_ops = [
        op
        for op in ops
        if op.op == "replace" and op.asr_idx is not None and op.ref_idx is not None
    ]
    if not replace_ops:
        # 全部 equal 或全部 insert/delete
        equal_count = sum(1 for op in ops if op.op == "equal")
        total = len(ops) or 1
        quality = equal_count / total
    else:
        similarities = []
        for op in replace_ops:
            assert op.asr_idx is not None and op.ref_idx is not None
            sim = fuzz_ratio(asr_lines[op.asr_idx], ref_lines[op.ref_idx]) / 100.0
            similarities.append(sim)
        equal_count = sum(1 for op in ops if op.op == "equal")
        total = len(ops) or 1
        avg_sim = sum(similarities) / len(similarities) if similarities else 0
        quality = (equal_count + avg_sim * len(replace_ops)) / total

    if quality < ALIGNMENT_QUALITY_THRESHOLD:
        raise AlignmentQualityError(
            f"文稿与音频内容差异过大（匹配度 {quality:.0%}），请检查文稿是否正确"
        )
    return quality
