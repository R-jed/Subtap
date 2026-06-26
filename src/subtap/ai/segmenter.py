"""SentenceEngine: unified sentence segmentation with spaCy PRIMARY + rule-based FALLBACK.

Architecture:
- PRIMARY: spaCy sentencizer (industrial-grade NLP)
- FALLBACK: rule-based splitter (when spaCy unavailable)
- POST: CPS limiter (always runs)

Rules:
- Only ONE primary implementation
- Fallback only triggers on primary failure
- No parallel decision paths
"""

from __future__ import annotations

import re
from subtap.schemas.models import SentenceSegment


# Maximum characters per line (Chinese)
MAX_CHARS_PER_LINE = 42

# Maximum characters per second (reading speed)
MAX_CPS = 15

# Punctuation that indicates sentence boundaries
SENTENCE_ENDINGS = set("。！？.!?")
SENTENCE_PAUSES = set("，,；;：:")


class SentenceEngine:
    """Unified sentence segmentation engine.

    Single decision path: spaCy PRIMARY → rule-based FALLBACK → CPS POST.
    """

    def __init__(self, use_spacy: bool = True):
        """Initialize sentence engine.

        Args:
            use_spacy: Whether to use spaCy as primary (controlled by DecisionEngine).
        """
        self._use_spacy = use_spacy
        self._spacy_nlp = None
        if use_spacy:
            self._init_spacy()

    def _init_spacy(self):
        """Initialize spaCy with fallback."""
        try:
            import spacy
            # Try Chinese model
            try:
                self._spacy_nlp = spacy.load("zh_core_web_sm")
            except OSError:
                # Fallback to English model
                try:
                    self._spacy_nlp = spacy.load("en_core_web_sm")
                except OSError:
                    self._spacy_nlp = None
        except ImportError:
            self._spacy_nlp = None

    def segment(
        self,
        texts: list[str],
        timings: list[tuple[float, float]],
        chunk_ids: list[int] | None = None,
    ) -> list[SentenceSegment]:
        """Full segmentation pipeline.

        Flow: PRIMARY/FALLBACK split → length balance → CPS limit.

        Args:
            texts: Cleaned text strings.
            timings: List of (start_sec, end_sec) tuples.
            chunk_ids: Optional chunk IDs.

        Returns:
            Optimized sentence segments.
        """
        if chunk_ids is None:
            chunk_ids = [0] * len(texts)

        # Step 1: Sentence split (PRIMARY or FALLBACK)
        sentences = self._split_sentences(texts, timings, chunk_ids)
        # Step 2: Balance length
        sentences = self._balance_length(sentences)
        # Step 3: CPS limit
        sentences = self._limit_cps(sentences)
        return sentences

    def _split_sentences(
        self,
        texts: list[str],
        timings: list[tuple[float, float]],
        chunk_ids: list[int],
    ) -> list[SentenceSegment]:
        """Split sentences using PRIMARY (spaCy) or FALLBACK (rule-based).

        Args:
            texts: Text strings to split.
            timings: Timing tuples.
            chunk_ids: Chunk IDs.

        Returns:
            Split sentence segments.
        """
        # PRIMARY: spaCy
        if self._use_spacy and self._spacy_nlp is not None:
            try:
                return self._spacy_split(texts, timings, chunk_ids)
            except Exception:
                pass  # Fall through to fallback

        # FALLBACK: rule-based
        return self._rule_based_split(texts, timings, chunk_ids)

    def _spacy_split(
        self,
        texts: list[str],
        timings: list[tuple[float, float]],
        chunk_ids: list[int],
    ) -> list[SentenceSegment]:
        """Split using spaCy sentencizer (PRIMARY).

        Args:
            texts: Text strings.
            timings: Timing tuples.
            chunk_ids: Chunk IDs.

        Returns:
            Sentence segments from spaCy.
        """
        result = []
        sentence_id = 0

        for text, (start, end), chunk_id in zip(texts, timings, chunk_ids):
            if not text:
                continue

            doc = self._spacy_nlp(text)
            sentences = [sent.text for sent in doc.sents]

            # Distribute time proportionally
            total_chars = sum(len(s) for s in sentences)
            current_time = start

            for sent_text in sentences:
                if not sent_text.strip():
                    continue

                # Calculate duration proportionally
                if total_chars > 0:
                    duration = (len(sent_text) / total_chars) * (end - start)
                else:
                    duration = (end - start) / len(sentences)

                result.append(SentenceSegment(
                    sentence_id=sentence_id,
                    chunk_id=chunk_id,
                    start_sec=current_time,
                    end_sec=current_time + duration,
                    text=sent_text.strip(),
                    source_text=sent_text.strip(),
                ))
                sentence_id += 1
                current_time += duration

        return result

    def _rule_based_split(
        self,
        texts: list[str],
        timings: list[tuple[float, float]],
        chunk_ids: list[int],
    ) -> list[SentenceSegment]:
        """Split on punctuation boundaries (FALLBACK).

        Args:
            texts: Text strings to split.
            timings: Timing tuples.
            chunk_ids: Chunk IDs.

        Returns:
            Split sentence segments.
        """
        result = []
        sentence_id = 0

        for text, (start, end), chunk_id in zip(texts, timings, chunk_ids):
            if not text:
                continue

            # Split on sentence-ending punctuation
            parts = re.split(r"([。！？.!?])", text)

            current_text = ""
            for part in parts:
                if part in SENTENCE_ENDINGS:
                    current_text += part
                    if current_text.strip():
                        result.append(SentenceSegment(
                            sentence_id=sentence_id,
                            chunk_id=chunk_id,
                            start_sec=start,
                            end_sec=end,
                            text=current_text.strip(),
                            source_text=current_text.strip(),
                        ))
                        sentence_id += 1
                    current_text = ""
                else:
                    current_text += part

            # Handle remaining text
            if current_text.strip():
                result.append(SentenceSegment(
                    sentence_id=sentence_id,
                    chunk_id=chunk_id,
                    start_sec=start,
                    end_sec=end,
                    text=current_text.strip(),
                    source_text=current_text.strip(),
                ))
                sentence_id += 1

        return result

    def _balance_length(self, segments: list[SentenceSegment]) -> list[SentenceSegment]:
        """Split long sentences to meet character limit.

        Args:
            segments: Segments to balance.

        Returns:
            Segments with length ≤ MAX_CHARS_PER_LINE.
        """
        result = []
        sentence_id = 0

        for seg in segments:
            text = seg.text

            if len(text) <= MAX_CHARS_PER_LINE:
                result.append(SentenceSegment(
                    sentence_id=sentence_id,
                    chunk_id=seg.chunk_id,
                    start_sec=seg.start_sec,
                    end_sec=seg.end_sec,
                    text=text,
                    source_text=text,
                ))
                sentence_id += 1
            else:
                # Split long text at natural boundaries
                parts = self._split_long_text(text, MAX_CHARS_PER_LINE)
                total_duration = seg.end_sec - seg.start_sec
                chars_per_part = [len(p) for p in parts]
                total_chars = sum(chars_per_part)

                current_time = seg.start_sec
                for i, part in enumerate(parts):
                    # Distribute time proportionally
                    part_duration = (chars_per_part[i] / total_chars) * total_duration if total_chars > 0 else 0
                    result.append(SentenceSegment(
                        sentence_id=sentence_id,
                        chunk_id=seg.chunk_id,
                        start_sec=current_time,
                        end_sec=current_time + part_duration,
                        text=part.strip(),
                        source_text=part.strip(),
                    ))
                    sentence_id += 1
                    current_time += part_duration

        return result

    def _limit_cps(self, segments: list[SentenceSegment]) -> list[SentenceSegment]:
        """Adjust timing to meet CPS constraint (POST).

        Args:
            segments: Sentence segments with timing.

        Returns:
            Segments with adjusted timing for reading speed.
        """
        result = []
        for seg in segments:
            duration = seg.end_sec - seg.start_sec
            if duration <= 0:
                result.append(seg)
                continue

            cps = len(seg.text) / duration
            if cps > MAX_CPS:
                # Extend duration to meet CPS constraint
                new_duration = len(seg.text) / MAX_CPS
                result.append(SentenceSegment(
                    sentence_id=seg.sentence_id,
                    chunk_id=seg.chunk_id,
                    start_sec=seg.start_sec,
                    end_sec=seg.start_sec + new_duration,
                    text=seg.text,
                    source_text=seg.source_text,
                ))
            else:
                result.append(seg)

        return result

    def _split_long_text(self, text: str, max_len: int) -> list[str]:
        """Split long text at natural boundaries.

        Args:
            text: Text to split.
            max_len: Maximum length per part.

        Returns:
            List of text parts.
        """
        if len(text) <= max_len:
            return [text]

        parts = []
        current = ""

        for char in text:
            current += char
            if len(current) >= max_len:
                # Try to split at punctuation
                if char in SENTENCE_PAUSES or char in SENTENCE_ENDINGS:
                    parts.append(current)
                    current = ""
                elif len(current) >= max_len:
                    # Force split
                    parts.append(current)
                    current = ""

        if current:
            parts.append(current)

        return parts
