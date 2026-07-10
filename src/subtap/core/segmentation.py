"""Sentence segmentation: RawCleanSegment → SentenceSegment.

Three-tier segmentation strategy for Chinese colloquial content:
1. Sentence-ending punctuation (。！？.!?)
2. Comma/pause punctuation (，、,;) for long sentences
3. jieba word boundary splitting for unpunctuated text
"""

from __future__ import annotations

import re

import jieba

from subtap.schemas.models import RawCleanSegment, SentenceSegment

# Max chars per sentence before forced split
_MAX_CHARS = 60

# Min chars for a sentence to be considered valid
# 低于此值的句子会被合并到相邻句子，减少字幕碎片
_MIN_CHARS = 10

# Sentence-ending punctuation
_SENT_END_RE = re.compile(r"[。！？.!?]+")

# Comma/pause punctuation (secondary split points)
_COMMA_RE = re.compile(r"[，、,;；]+")


def _split_sentences(text: str, language: str = "zh") -> list[str]:
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

    return _split_sentences_zh(text)


def _split_sentences_zh(text: str) -> list[str]:
    """Chinese sentence segmentation with three-tier strategy."""

    # Tier 1: Split at sentence-ending punctuation
    parts = _split_at_pattern(text, _SENT_END_RE)

    # Tier 2: For each part, split long sentences at comma/pause
    expanded: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) > _MAX_CHARS:
            expanded.extend(_split_at_comma(part))
        else:
            expanded.append(part)

    # Tier 3: For any remaining long segments, split at word boundary
    result: list[str] = []
    for sent in expanded:
        if len(sent) > _MAX_CHARS:
            result.extend(_split_at_word_boundary(sent, _MAX_CHARS))
        else:
            result.append(sent)

    # Merge very short sentences
    result = _merge_short_sentences(result, _MIN_CHARS)

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


def _split_at_comma(text: str) -> list[str]:
    """Split long text at comma/pause punctuation.

    Tries to split at natural pause points while keeping segments ≤ _MAX_CHARS.
    """
    if len(text) <= _MAX_CHARS:
        return [text]

    segments: list[str] = []
    current = ""

    # Split at each comma, accumulate until max_chars
    parts = _COMMA_RE.split(text)
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        if current and len(current) + len(part) + 1 > _MAX_CHARS:
            segments.append(current.strip())
            current = part
        else:
            current = current + "，" + part if current else part

    if current.strip():
        segments.append(current.strip())

    # If any segment is still too long, fall back to word boundary splitting
    result: list[str] = []
    for seg in segments:
        if len(seg) > _MAX_CHARS:
            result.extend(_split_at_word_boundary(seg, _MAX_CHARS))
        else:
            result.append(seg)

    return result


def _split_at_word_boundary(text: str, max_chars: int) -> list[str]:
    """Split long text at Chinese word boundaries using jieba.

    Args:
        text: Text to split.
        max_chars: Maximum characters per segment.

    Returns:
        List of text segments.
    """
    if len(text) <= max_chars:
        return [text]

    words = list(jieba.cut(text))

    parts: list[str] = []
    current = ""

    for word in words:
        if len(current) + len(word) > max_chars and current:
            parts.append(current.strip())
            current = word
        else:
            current += word

    if current.strip():
        parts.append(current.strip())

    return parts


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

    merged: list[str] = []
    buffer = ""

    for sent in sentences:
        if buffer:
            # Don't merge if buffer ends with sentence-ending punctuation
            if buffer and buffer[-1] in _SENT_END_CHARS:
                merged.append(buffer)
                buffer = sent
            elif len(buffer) < min_chars:
                buffer += sent
            else:
                merged.append(buffer)
                buffer = sent
        else:
            buffer = sent

    if buffer:
        if (
            merged
            and len(buffer) < min_chars
            and (not merged[-1] or merged[-1][-1] not in _SENT_END_CHARS)
        ):
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
        parts = _split_sentences(seg.cleaned_text, language=language)
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
