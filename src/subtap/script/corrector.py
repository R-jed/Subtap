"""In-sentence correction using rapidfuzz."""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz.fuzz import ratio as fuzz_ratio
from rapidfuzz.distance import Levenshtein

from subtap.script.aligner import AlignOp, CORRECTION_THRESHOLD


@dataclass
class CorrectionResult:
    """Result of a single text correction."""
    original: str
    corrected: str
    similarity: float
    corrected_flag: bool
    changes: list[tuple[str, int, int]] = field(default_factory=list)


def correct_text(asr_text: str, ref_text: str) -> CorrectionResult:
    """Correct ASR text using reference text.

    Args:
        asr_text: ASR output text.
        ref_text: Reference manuscript text.

    Returns:
        CorrectionResult with corrected text and metadata.
    """
    sim = fuzz_ratio(asr_text, ref_text) / 100.0

    if sim >= CORRECTION_THRESHOLD and asr_text != ref_text:
        ops = Levenshtein.editops(asr_text, ref_text)
        changes = [(op, src_pos, dst_pos) for op, src_pos, dst_pos in ops]
        return CorrectionResult(
            original=asr_text,
            corrected=ref_text,
            similarity=sim,
            corrected_flag=True,
            changes=changes,
        )

    return CorrectionResult(
        original=asr_text,
        corrected=asr_text,
        similarity=sim,
        corrected_flag=False,
    )


def correct_segments(
    segments: list[dict],
    align_ops: list[AlignOp],
    ref_lines: list[str],
) -> tuple[list[dict], int]:
    """Correct segments based on alignment operations.

    Args:
        segments: ASR segments (list of dicts with text, start_sec, end_sec).
        align_ops: Alignment operations from aligner.
        ref_lines: Reference manuscript lines.

    Returns:
        Tuple of (corrected segments list, skipped count).
    """
    result = []
    skipped = 0

    for op in align_ops:
        if op.op == "equal":
            # 保留原文
            item = dict(segments[op.asr_idx])
            result.append(item)

        elif op.op == "replace" and op.asr_idx is not None and op.ref_idx is not None:
            asr_seg = segments[op.asr_idx]
            ref_text = ref_lines[op.ref_idx]
            correction = correct_text(asr_seg["text"], ref_text)

            item = dict(asr_seg)
            if correction.corrected_flag:
                item["text"] = correction.corrected
                item["source_text"] = asr_seg["text"]
            else:
                skipped += 1

            result.append(item)

        elif op.op == "delete" and op.asr_idx is not None:
            # ASR 多出 → 保留原文
            item = dict(segments[op.asr_idx])
            result.append(item)

        elif op.op == "insert":
            # 文稿多出 → 跳过（无时间轴）
            continue

    return result, skipped