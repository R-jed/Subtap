"""Hotword replacement engine — local rules + LLM."""

from __future__ import annotations

from pathlib import Path

from subtap.glossary.hotword import (
    Hotword,
    HotwordGlossary,
    load_glossary,
)


def replace_exact(text: str, old: str, new: str) -> str:
    """Replace exact match in text."""
    return text.replace(old, new)


def replace_in_text(text: str, glossary: HotwordGlossary) -> str:
    """Replace all hotwords in text using glossary."""
    aliases = glossary.get_all_aliases()
    # Sort by length descending to avoid partial matches
    sorted_aliases = sorted(aliases.keys(), key=len, reverse=True)
    for alias in sorted_aliases:
        word = aliases[alias]
        if alias in text:
            text = text.replace(alias, word)
    return text


class HotwordEngine:
    """Hotword replacement engine."""

    def __init__(
        self,
        mode: str = "local",
        glossary_dir: Path | None = None,
    ):
        self.mode = mode
        self.glossary_dir = glossary_dir or Path.home() / ".subtap" / "glossary"
        self._glossaries: dict[str, HotwordGlossary] = {}

    def _load_glossary(self, lang: str) -> HotwordGlossary:
        """Load glossary for language."""
        if lang not in self._glossaries:
            path = self.glossary_dir / f"hotwords_{lang}.tsv"
            self._glossaries[lang] = load_glossary(path, lang)
        return self._glossaries[lang]

    def process(self, text: str, lang: str = "zh") -> str:
        """Process text with hotword replacement."""
        glossary = self._load_glossary(lang)
        if not glossary.hotwords:
            return text

        # Local rule-based replacement
        text = replace_in_text(text, glossary)

        # TODO: LLM-based replacement for hybrid/api mode
        # if self.mode in ("hybrid", "api"):
        #     text = self._llm_replace(text, glossary)

        return text

    def process_batch(self, texts: list[str], lang: str = "zh") -> list[str]:
        """Process multiple texts."""
        return [self.process(text, lang) for text in texts]
