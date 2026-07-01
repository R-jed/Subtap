"""Sentence segmentation: CleanSegment → SentenceSegment.

Uses pySBD for sentence boundary detection and jieba for Chinese word segmentation.
"""

from __future__ import annotations

import pysbd
import jieba

from subtap.schemas.models import CleanSegment, SentenceSegment

# Max chars per sentence before forced split at word boundary
_MAX_CHARS = 60

# Min chars for a sentence to be considered valid
_MIN_CHARS = 5


def _split_sentences(text: str, language: str = "zh") -> list[str]:
    """Split text into sentences using pySBD + jieba.

    Args:
        text: Input text to split.
        language: Language code ("zh" or "en").

    Returns:
        List of sentence strings.
    """
    if not text.strip():
        return []

    # Step 1: Use pySBD for sentence boundary detection
    lang = "zh" if language in ("zh", "ja") else "en"
    segmenter = pysbd.Segmenter(language=lang, clean=False)
    raw_sentences = segmenter.segment(text)

    # Step 2: Split long sentences at word boundaries using jieba
    sentences: list[str] = []
    for sent in raw_sentences:
        sent = sent.strip()
        if not sent:
            continue

        if len(sent) > _MAX_CHARS:
            # Split at word boundary
            parts = _split_at_word_boundary(sent, _MAX_CHARS)
            sentences.extend(parts)
        else:
            sentences.append(sent)

    # Step 3: Merge very short sentences
    sentences = _merge_short_sentences(sentences, _MIN_CHARS)

    return sentences if sentences else [""]


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

    # Use jieba to tokenize
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

    Args:
        sentences: List of sentences.
        min_chars: Minimum characters for a valid sentence.

    Returns:
        List of merged sentences.
    """
    if not sentences:
        return []

    merged: list[str] = []
    buffer = ""

    for sent in sentences:
        if buffer:
            # If buffer is still short, merge with current
            if len(buffer) < min_chars:
                buffer += sent
            else:
                merged.append(buffer)
                buffer = sent
        else:
            buffer = sent

    if buffer:
        if merged and len(buffer) < min_chars:
            # Merge last short sentence with previous
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
    segments: list[CleanSegment],
    chunk_start: float = 0.0,
    chunk_end: float = 1.0,
    language: str = "zh",
) -> list[SentenceSegment]:
    """Split CleanSegments into SentenceSegments.

    Uses pySBD for sentence boundary detection and jieba for word-boundary splitting.

    Args:
        segments: CleanSegments from the clean stage.
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
                    source_text=seg.cleaned_text,
                )
            )
            sid += 1

    return sentences
