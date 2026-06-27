"""CleanEngine: unified ASR post-processing with deterministic PRIMARY + optional ENHANCER.

Architecture:
- PRIMARY: regex + deterministic cleanup (always runs)
- ENHANCER: spaCy/nltk punctuation restore (optional, controlled by DecisionEngine)
- ENHANCER: rapidfuzz fuzzy matching (optional, controlled by DecisionEngine)

Rules:
- Deterministic MUST run first
- AI cannot change semantics, only enhance
- No parallel decision paths
"""

from __future__ import annotations

import re
from typing import Optional

from subtap.schemas.models import ASRSegment

# Filler words to remove (English + Chinese)
FILLER_WORDS_EN = {"um", "uh", "ah", "er", "like", "you know"}
FILLER_WORDS_ZH = {"这个", "那个", "嗯", "啊", "呃", "就是说"}


class CleanEngine:
    """Unified ASR post-processing engine.

    Single decision path: deterministic PRIMARY → optional ENHANCER.
    """

    def __init__(self, use_spacy: bool = False, use_fuzzy: bool = False):
        """Initialize clean engine.

        Args:
            use_spacy: Whether to use spaCy for punctuation restore (controlled by DecisionEngine).
            use_fuzzy: Whether to use rapidfuzz for fuzzy matching (controlled by DecisionEngine).
        """
        self._use_spacy = use_spacy
        self._use_fuzzy = use_fuzzy
        self._spacy_nlp = None
        self._rapidfuzz_available = False

        if use_spacy:
            self._init_spacy()
        if use_fuzzy:
            self._init_rapidfuzz()

    def _init_spacy(self):
        """Initialize spaCy for punctuation restore."""
        try:
            import spacy

            try:
                self._spacy_nlp = spacy.load("zh_core_web_sm")
            except OSError:
                try:
                    self._spacy_nlp = spacy.load("en_core_web_sm")
                except OSError:
                    self._spacy_nlp = None
        except ImportError:
            self._spacy_nlp = None

    def _init_rapidfuzz(self):
        """Initialize rapidfuzz for fuzzy matching."""
        import importlib.util

        self._rapidfuzz_available = importlib.util.find_spec("rapidfuzz") is not None

    def process(
        self,
        segments: list[ASRSegment],
        glossary: Optional[dict[str, str]] = None,
    ) -> list[ASRSegment]:
        """Full ASR post-processing pipeline.

        Flow: deterministic PRIMARY → optional ENHANCER.

        Args:
            segments: Raw ASR segments.
            glossary: Optional term normalization dict.

        Returns:
            Enhanced ASR segments.
        """
        # PRIMARY: deterministic cleanup (always runs)
        result = self._remove_fillers(segments)
        result = self._restore_punctuation(result)
        result = self._normalize_entities(result, glossary_terms=glossary)
        return result

    def _remove_fillers(self, segments: list[ASRSegment]) -> list[ASRSegment]:
        """Remove filler words from ASR output (PRIMARY).

        Uses regex for lightweight filler removal.

        Args:
            segments: ASR segments with potential filler words.

        Returns:
            Segments with fillers removed.
        """
        result = []
        for seg in segments:
            text = seg.text
            # Remove English fillers (word boundary matching)
            for filler in FILLER_WORDS_EN:
                text = re.sub(rf"\b{filler}\b", "", text, flags=re.IGNORECASE)
            # Remove Chinese fillers
            for filler in FILLER_WORDS_ZH:
                text = text.replace(filler, "")
            # Clean up extra spaces
            text = re.sub(r"\s+", " ", text).strip()
            result.append(
                ASRSegment(
                    chunk_id=seg.chunk_id,
                    segment_id=seg.segment_id,
                    text=text,
                    start_sec=seg.start_sec,
                    end_sec=seg.end_sec,
                    confidence=seg.confidence,
                )
            )
        return result

    def _restore_punctuation(self, segments: list[ASRSegment]) -> list[ASRSegment]:
        """Restore punctuation using spaCy ENHANCER with rule-based fallback.

        Priority:
        1. spaCy (if enabled and available)
        2. Rule-based (always available)

        Args:
            segments: ASR segments without punctuation.

        Returns:
            Segments with restored punctuation.
        """
        result = []
        for seg in segments:
            text = seg.text
            if not text:
                result.append(seg)
                continue

            # ENHANCER: spaCy (if enabled)
            if self._use_spacy and self._spacy_nlp is not None:
                try:
                    doc = self._spacy_nlp(text)
                    sentences = [sent.text for sent in doc.sents]
                    text = " ".join(sentences)
                except Exception:
                    pass  # Fall through to rule-based

            # PRIMARY: rule-based fallback
            if text and text[-1] not in "。！？.!?，,；;：:）)】」』" "）)]}":
                text = text + "。"

            result.append(
                ASRSegment(
                    chunk_id=seg.chunk_id,
                    segment_id=seg.segment_id,
                    text=text,
                    start_sec=seg.start_sec,
                    end_sec=seg.end_sec,
                    confidence=seg.confidence,
                )
            )
        return result

    def _normalize_entities(
        self,
        segments: list[ASRSegment],
        glossary_terms: Optional[dict[str, str]] = None,
    ) -> list[ASRSegment]:
        """Normalize entities using rapidfuzz ENHANCER with exact match fallback.

        Priority:
        1. rapidfuzz fuzzy matching (if enabled)
        2. Exact string replacement (always available)

        Args:
            segments: ASR segments.
            glossary_terms: Optional term normalization dict (original → normalized).

        Returns:
            Segments with normalized entities.
        """
        if not glossary_terms:
            return segments

        result = []
        for seg in segments:
            text = seg.text

            # ENHANCER: rapidfuzz (if enabled)
            if self._use_fuzzy and self._rapidfuzz_available:
                try:
                    from rapidfuzz import fuzz, process

                    for original, normalized in glossary_terms.items():
                        # Find best match in text
                        matches = process.extract(
                            original,
                            text.split(),
                            scorer=fuzz.ratio,
                            score_cutoff=80,
                        )
                        for match_text, score, idx in matches:
                            if score >= 80:
                                text = text.replace(match_text, normalized)
                except Exception:
                    # Fallback to exact replacement
                    for original, normalized in glossary_terms.items():
                        text = text.replace(original, normalized)
            else:
                # PRIMARY: exact string replacement
                for original, normalized in glossary_terms.items():
                    text = text.replace(original, normalized)

            result.append(
                ASRSegment(
                    chunk_id=seg.chunk_id,
                    segment_id=seg.segment_id,
                    text=text,
                    start_sec=seg.start_sec,
                    end_sec=seg.end_sec,
                    confidence=seg.confidence,
                )
            )
        return result
