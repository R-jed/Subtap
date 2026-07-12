"""Sentence segmentation: RawCleanSegment → SentenceSegment.

Stable-ts style segmentation strategy for Chinese colloquial content:
1. Sentence-ending punctuation (。！？.!?)
2. Comma/pause punctuation (，、,;) for long sentences
3. Force split by max_chars
4. Merge short segments

Algorithm reference: https://github.com/jianfch/stable-ts
"""

from __future__ import annotations

import re

from subtap.schemas.models import RawCleanSegment, SentenceSegment

_DEFAULT_MAX_CHARS = 25
_DEFAULT_MIN_CHARS = 10

# Sentence-ending punctuation
_SENT_END_RE = re.compile(r"[。！？.!?]+")

# Comma/pause punctuation (secondary split points)
_COMMA_RE = re.compile(r"[，、,;；]+")


def _split_sentences(
    text: str,
    language: str = "zh",
    max_chars: int = _DEFAULT_MAX_CHARS,
    min_chars: int = _DEFAULT_MIN_CHARS,
) -> list[str]:
    """Split text into sentences using tiered strategy.

    Args:
        text: Input text to split.
        language: Language code ("zh" or "en").

    Returns:
        List of sentence strings.
    """
    if not text.strip():
        return [""]

    if language in ("en",):
        return _split_sentences_en(text)

    return _split_sentences_zh(text, max_chars=max_chars, min_chars=min_chars)


def _split_sentences_zh(
    text: str,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    min_chars: int = _DEFAULT_MIN_CHARS,
) -> list[str]:
    """Chinese sentence segmentation with stable-ts style strategy."""

    # Tier 1: Split at sentence-ending punctuation
    segments = _split_at_pattern(text, _SENT_END_RE)

    # Tier 2: For long segments, split at comma/pause
    expanded: list[str] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) > max_chars:
            expanded.extend(_split_at_comma(seg, max_chars))
        else:
            expanded.append(seg)

    # Tier 3: Force split any remaining long segments by max_chars
    result: list[str] = []
    for seg in expanded:
        if len(seg) > max_chars:
            result.extend(_split_by_length(seg, max_chars))
        else:
            result.append(seg)

    # Merge very short sentences
    result = _merge_short_sentences(result, min_chars)

    return result if result else [""]


def _split_sentences_en(text: str) -> list[str]:
    """English sentence segmentation."""
    parts = _split_at_pattern(text, _SENT_END_RE)
    result = [p.strip() for p in parts if p.strip()]
    return result if result else [""]


def _split_at_pattern(text: str, pattern: re.Pattern) -> list[str]:
    """Split text at regex pattern boundaries, keeping delimiters attached.

    Args:
        text: Text to split.
        pattern: Regex pattern to split at.

    Returns:
        List of text segments with punctuation attached to preceding text.
    """
    segments: list[str] = []
    last_end = 0

    for match in pattern.finditer(text):
        end = match.end()
        segment = text[last_end:end]
        if segment.strip():
            segments.append(segment)
        last_end = end

    # Remaining text after last punctuation
    remaining = text[last_end:]
    if remaining.strip():
        segments.append(remaining)

    return segments


def _split_at_comma(text: str, max_chars: int = _DEFAULT_MAX_CHARS) -> list[str]:
    """Split long text at comma/pause punctuation.

    Tries to split at natural pause points while keeping segments within max_chars.
    """
    if len(text) <= max_chars:
        return [text]

    segments: list[str] = []
    current = ""

    # Split at each comma, accumulate until max_chars
    parts = _COMMA_RE.split(text)
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        if current and len(current) + len(part) + 1 > max_chars:
            segments.append(current.strip())
            current = part
        else:
            current = current + "，" + part if current else part

    if current.strip():
        segments.append(current.strip())

    # If any segment is still too long, force split by max_chars
    result: list[str] = []
    for seg in segments:
        if len(seg) > max_chars:
            result.extend(_split_by_length(seg, max_chars))
        else:
            result.append(seg)

    return result


def _split_by_length(text: str, max_chars: int) -> list[str]:
    """Force split text by max_chars length.

    Args:
        text: Text to split.
        max_chars: Maximum characters per segment.

    Returns:
        List of text segments.
    """
    if len(text) <= max_chars:
        return [text]

    segments: list[str] = []
    for i in range(0, len(text), max_chars):
        segments.append(text[i : i + max_chars])

    return segments


def _merge_short_sentences(sentences: list[str], min_chars: int) -> list[str]:
    """Merge sentences that are too short.

    Preserves sentence-ending punctuation boundaries: sentences ending with
    。！？.!? are never merged with adjacent sentences, even if short.

    Args:
        sentences: List of sentences.
        min_chars: Minimum characters for a valid sentence.

    Returns:
        List of merged sentences.
    """
    if not sentences:
        return []

    _SENT_END_CHARS = set("。！？.!?")

    # If all sentences are short, don't merge (preserve original structure)
    if all(len(s) < min_chars for s in sentences):
        return sentences

    merged: list[str] = []
    buffer = ""

    for seg in sentences:
        if buffer:
            # If buffer ends with sentence-ending punctuation, don't merge
            if buffer and buffer[-1] in _SENT_END_CHARS:
                merged.append(buffer)
                buffer = seg
            # If buffer is long enough, output and start new segment
            elif len(buffer) >= min_chars:
                merged.append(buffer)
                buffer = seg
            # Otherwise merge
            else:
                buffer += seg
        else:
            buffer = seg

    if buffer:
        # If last buffer ends with sentence-ending punctuation, don't merge
        if buffer[-1] in _SENT_END_CHARS:
            merged.append(buffer)
        elif merged and len(buffer) < min_chars:
            merged[-1] += buffer
        else:
            merged.append(buffer)

    return merged


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
    segments: list[RawCleanSegment],
    chunk_start: float = 0.0,
    chunk_end: float = 1.0,
    language: str = "zh",
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    min_chars: int = _DEFAULT_MIN_CHARS,
) -> list[SentenceSegment]:
    """Split RawCleanSegments into SentenceSegments.

    Args:
        segments: RawCleanSegments from the clean stage.
        chunk_start: Start time of the source chunk.
        chunk_end: End time of the source chunk.
        language: Language code ("zh" or "en").
    """
    if not segments:
        return []

    n_segs = len(segments)
    chunk_duration = chunk_end - chunk_start
    seg_duration = chunk_duration / n_segs

    sentences: list[SentenceSegment] = []
    sid = 0

    for i, seg in enumerate(segments):
        parts = _split_sentences(
            seg.cleaned_text,
            language=language,
            max_chars=max_chars,
            min_chars=min_chars,
        )
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
                    source_text=text,
                )
            )
            sid += 1

    return sentences
