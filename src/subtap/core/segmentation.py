"""Sentence segmentation: RawCleanSegment → SentenceSegment.

Stable-ts style segmentation strategy for Chinese colloquial content:
1. Sentence-ending punctuation (。！？.!?)
2. Preserve comma clauses until forced alignment provides acoustic timing
3. Defer display-length splitting until acoustic timing is available

Display-length splitting is deferred until forced alignment provides acoustic
timing, so this stage cannot cut a Chinese word at an arbitrary character.

Algorithm reference: https://github.com/jianfch/stable-ts
"""

from __future__ import annotations

import re
import unicodedata

from subtap.schemas.models import RawCleanSegment, SentenceSegment

_DEFAULT_MAX_CHARS = 25

# Sentence-ending punctuation. A dot before an ASCII letter/digit belongs to a
# decimal or dotted initialism; the final dot in an initialism is protected by
# the fixed-width lookbehind.
_SENT_END_RE = re.compile(r"[。！？!?]+|(?<![A-Za-z]\.[A-Za-z])\.+(?![A-Za-z0-9])")

# Comma/pause punctuation (secondary split points)
_COMMA_RE = re.compile(r"[，、,;；]+")
_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _split_sentences(
    text: str,
    language: str = "zh",
    max_chars: int = _DEFAULT_MAX_CHARS,
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

    return _split_sentences_zh(text, max_chars=max_chars)


def _split_sentences_zh(
    text: str,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> list[str]:
    """Chinese sentence segmentation with stable-ts style strategy."""

    # Tier 1: Split at sentence-ending punctuation
    segments = _split_at_pattern(text, _SENT_END_RE)

    # Comma clauses are not independent sentences. Splitting them here creates
    # irreversible boundaries before acoustic pauses and word timing exist.
    # The export stage owns display-width splitting after forced alignment.
    expanded = [seg.strip() for seg in segments if seg.strip()]

    # Latin text has explicit word boundaries and is safe to length-split here.
    # CJK display splitting waits for acoustic timing in the export stage.
    length_safe: list[str] = []
    for seg in expanded:
        if len(seg) > max_chars and not _CJK_RE.search(seg):
            length_safe.extend(_split_at_word_boundary(seg, max_chars))
        else:
            length_safe.append(seg)

    return length_safe if length_safe else [""]


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

    # Keep each original delimiter attached to the preceding text.
    parts: list[str] = []
    last_end = 0
    for match in _COMMA_RE.finditer(text):
        parts.append(text[last_end : match.end()])
        last_end = match.end()
    if last_end < len(text):
        parts.append(text[last_end:])

    for part in parts:
        if current and len(current) + len(part) > max_chars:
            segments.append(current)
            current = part
        else:
            current += part

    if current:
        segments.append(current)

    return segments


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


def _split_at_word_boundary(text: str, max_chars: int) -> list[str]:
    """Force-split text while preserving a Latin word when possible."""
    result: list[str] = []
    start = 0
    while len(text) - start > max_chars:
        end = start + max_chars
        while (
            end > start
            and text[end - 1].isascii()
            and text[end - 1].isalnum()
            and text[end].isascii()
            and text[end].isalnum()
        ):
            end -= 1
        if end == start:
            end = start + max_chars
            while (
                end < len(text)
                and text[end - 1].isascii()
                and text[end - 1].isalnum()
                and text[end].isascii()
                and text[end].isalnum()
            ):
                end += 1
        while end < len(text) and unicodedata.category(text[end]).startswith("P"):
            end += 1
        result.append(text[start:end])
        start = end
    result.append(text[start:])
    return result


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
