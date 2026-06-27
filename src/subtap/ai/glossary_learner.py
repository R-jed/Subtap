"""Glossary learner: detect repeated errors, extract domain terms, learn correction patterns.

Uses open-source libraries:
- rapidfuzz: fuzzy string matching for error detection
- regex: pattern mining from corrections

All external dependencies are optional with fallback to rule-based.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from subtap.schemas.models import ASRSegment


@dataclass
class GlossaryUpdate:
    """Glossary update suggestions from learning."""

    new_terms: dict[str, str] = field(default_factory=dict)
    replacement_rules: list[dict[str, str]] = field(default_factory=list)
    error_patterns: list[str] = field(default_factory=list)


class GlossaryLearner:
    """Learn glossary updates from ASR errors and user corrections.

    Uses rapidfuzz for fuzzy matching with rule-based fallback.
    """

    def __init__(self):
        self._rapidfuzz_available = False
        self._init_rapidfuzz()

    def _init_rapidfuzz(self):
        """Initialize rapidfuzz with fallback."""
        import importlib.util

        self._rapidfuzz_available = importlib.util.find_spec("rapidfuzz") is not None

    def learn(
        self,
        asr_segments: list[ASRSegment],
        corrections: list[dict],
    ) -> GlossaryUpdate:
        """Full learning pipeline.

        Args:
            asr_segments: ASR segments with potential errors.
            corrections: User corrections [{original, corrected, count}].

        Returns:
            GlossaryUpdate with suggestions.
        """
        # Detect repeated errors
        repeated_errors = self.detect_repeated_errors(asr_segments)

        # Extract domain terms
        domain_terms = self.extract_domain_terms(asr_segments)

        # Learn correction patterns
        patterns = self.learn_correction_patterns(corrections)

        # Build update
        new_terms = {}
        for term in domain_terms:
            new_terms[term] = term

        replacement_rules = []
        for error_term, count in repeated_errors.items():
            replacement_rules.append(
                {
                    "from": error_term,
                    "to": error_term,  # User should specify correction
                    "count": str(count),
                }
            )

        return GlossaryUpdate(
            new_terms=new_terms,
            replacement_rules=replacement_rules,
            error_patterns=patterns,
        )

    def detect_repeated_errors(
        self,
        segments: list[ASRSegment],
        min_occurrences: int = 2,
    ) -> dict[str, int]:
        """Detect terms that appear multiple times (potential errors).

        Uses rapidfuzz for fuzzy matching with Counter fallback.

        Args:
            segments: ASR segments.
            min_occurrences: Minimum count to be considered repeated.

        Returns:
            Dict of term → occurrence count.
        """
        # Count word/phrase occurrences
        word_counts: Counter[str] = Counter()

        for seg in segments:
            # Simple word extraction (split on spaces and punctuation)
            words = seg.text.split()
            for word in words:
                # Clean punctuation
                clean_word = word.strip("。！？.!?，,；;：:")
                if clean_word:
                    word_counts[clean_word] += 1

        # Filter by minimum occurrences
        repeated = {
            word: count
            for word, count in word_counts.items()
            if count >= min_occurrences
        }

        # If rapidfuzz available, find fuzzy similar terms
        if self._rapidfuzz_available and len(repeated) > 1:
            try:
                from rapidfuzz import fuzz

                terms = list(repeated.keys())
                for i in range(len(terms)):
                    for j in range(i + 1, len(terms)):
                        score = fuzz.ratio(terms[i], terms[j])
                        if score >= 80:  # 80% similar
                            # Merge counts
                            repeated[terms[i]] = repeated.get(
                                terms[i], 0
                            ) + repeated.get(terms[j], 0)
            except Exception:
                pass  # Use basic counts

        return repeated

    def extract_domain_terms(self, segments: list[ASRSegment]) -> list[str]:
        """Extract potential domain-specific terms.

        Simple heuristic: terms with high confidence and technical patterns.

        Args:
            segments: ASR segments.

        Returns:
            List of potential domain terms.
        """
        import re

        terms = set()

        for seg in segments:
            text = seg.text

            # English technical terms (uppercase, acronyms)
            english_terms = re.findall(r"\b[A-Z][A-Z]+\b", text)
            terms.update(english_terms)

            # Chinese technical terms (common patterns)
            if "学习" in text or "算法" in text or "模型" in text:
                for word in text.split():
                    if any(
                        keyword in word
                        for keyword in ["学习", "算法", "模型", "神经", "网络"]
                    ):
                        terms.add(word)

        return list(terms)

    def learn_correction_patterns(self, corrections: list[dict]) -> list[str]:
        """Learn patterns from user corrections.

        Args:
            corrections: User corrections [{original, corrected, count}].

        Returns:
            List of error pattern descriptions.
        """
        patterns = []

        for correction in corrections:
            original = correction.get("original", "")
            corrected = correction.get("corrected", "")
            count = correction.get("count", 0)

            if original and corrected and count > 0:
                patterns.append(f"{original} → {corrected} (出现 {count} 次)")

        return patterns
