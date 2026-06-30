"""Sentence segmentation: CleanSegment → SentenceSegment.

Deterministic rule-based splitter. No LLM, no external deps.
"""

from __future__ import annotations

import re

from subtap.schemas.models import CleanSegment, SentenceSegment

# Split rules:
# - CJK punctuation (。！？): always split (no space required)
# - Latin punctuation (.!?): only split when followed by whitespace or end
#   This preserves "0.6", "HighLightDiffusion.Filter", abbreviations etc.
_SENTENCE_RE = re.compile(r"(?<=[。！？])|(?<=[.!?])(?=\s)")

# Max chars per sentence before forced split
_MAX_CHARS = 80


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences by punctuation + length rules."""
    parts = _SENTENCE_RE.split(text)
    sentences: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Force-split long segments at word boundaries
        while len(part) > _MAX_CHARS:
            cut = part.rfind(" ", 0, _MAX_CHARS)
            if cut <= 0:
                cut = _MAX_CHARS
            sentences.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            sentences.append(part)
    return sentences or [""]


def _allocate_time(
    sentences: list[str],
    start_sec: float,
    end_sec: float,
) -> list[tuple[float, float]]:
    """Allocate time by character ratio within [start_sec, end_sec].

    Last sentence gets exact end to avoid float drift.
    """
    if not sentences:
        return []

    total_chars = max(sum(len(s) for s in sentences), 1)
    duration = end_sec - start_sec
    times: list[tuple[float, float]] = []
    cursor = start_sec

    for i, sent in enumerate(sentences):
        seg_dur = duration * len(sent) / total_chars
        seg_end = end_sec if i == len(sentences) - 1 else cursor + seg_dur
        times.append((round(cursor, 3), round(seg_end, 3)))
        cursor = seg_end

    return times


def segment_clean_segments(
    segments: list[CleanSegment],
    chunk_start: float = 0.0,
    chunk_end: float = 1.0,
) -> list[SentenceSegment]:
    """Split CleanSegments into SentenceSegments.

    Rules:
    - Split on 。！？.!? punctuation
    - Force-split at >80 chars
    - No cross-chunk merge
    - Time allocated by character ratio (no regression)

    Args:
        segments: CleanSegments from the clean stage.
        chunk_start: Start time of the source chunk.
        chunk_end: End time of the source chunk.
    """
    if not segments:
        return []

    n_segs = len(segments)
    chunk_duration = chunk_end - chunk_start
    seg_duration = chunk_duration / n_segs

    sentences: list[SentenceSegment] = []
    sid = 0

    for i, seg in enumerate(segments):
        parts = _split_sentences(seg.cleaned_text)
        seg_start = chunk_start + i * seg_duration
        seg_end = seg_start + seg_duration

        times = _allocate_time(parts, seg_start, seg_end)

        for text, (t_start, t_end) in zip(parts, times):
            sentences.append(
                SentenceSegment(
                    sentence_id=sid,
                    chunk_id=seg.source_chunk_id,
                    start_sec=t_start,
                    end_sec=t_end,
                    text=text,
                    source_text=seg.cleaned_text,
                )
            )
            sid += 1

    return sentences
