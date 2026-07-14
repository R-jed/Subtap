"""Runtime hotword glossary backed by the canonical YAML glossary."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from subtap.schemas.glossary import (
    Glossary,
    GlossaryTerm,
    load_glossary as load_yaml_glossary,
    save_glossary as save_yaml_glossary,
)


@dataclass
class Hotword:
    """A single hotword entry."""

    word: str
    aliases: list[str] = field(default_factory=list)


class HotwordGlossary:
    """Hotword glossary for a specific language."""

    def __init__(
        self,
        lang: str,
        hotwords: list[Hotword] | None = None,
        document: Glossary | None = None,
    ):
        self.lang = lang
        self.hotwords: list[Hotword] = []
        self._document = document or Glossary()
        for hotword in hotwords or []:
            self.add(hotword)

    def add(self, hotword: Hotword) -> None:
        """Add a hotword or merge aliases into its existing canonical term."""
        for existing in self.hotwords:
            if existing.word == hotword.word:
                existing.aliases.extend(
                    alias for alias in hotword.aliases if alias not in existing.aliases
                )
                return
        self.hotwords.append(hotword)

    def add_alias(self, word: str, alias: str) -> None:
        """Add an alias to existing hotword or create new one."""
        self.add(Hotword(word=word, aliases=[alias]))

    def remove(self, word: str) -> None:
        """Remove a hotword by word."""
        self.hotwords = [hw for hw in self.hotwords if hw.word != word]

    def find_by_alias(self, alias: str) -> Hotword | None:
        """Find hotword by alias."""
        for hw in self.hotwords:
            if alias in hw.aliases or alias == hw.word:
                return hw
        return None

    def get_all_aliases(self) -> dict[str, str]:
        """Get mapping of alias -> word."""
        result = {}
        for hw in self.hotwords:
            for alias in hw.aliases:
                result[alias] = hw.word
            result[hw.word] = hw.word
        return result

    def replace_in_text(self, text: str) -> str:
        """Replace all hotwords in text. Sorts by length descending to avoid partial matches.

        Skips self-replacements (alias == word) and prevents duplicate creation
        when the word already appears adjacent to the alias.
        """
        aliases = self.get_all_aliases()
        if not aliases:
            return text
        sorted_aliases = sorted(aliases.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            word = aliases[alias]
            if alias == word or alias not in text:
                continue
            # Prevent duplicate: skip if word already adjacent to alias
            # e.g., "VITURE维图尔" should not become "VITUREVITURE"
            new_text = text.replace(alias, word)
            if word + word not in new_text:
                text = new_text
        return text

    def get_applied_replacements(self, text: str) -> dict[str, str]:
        """Get the replacement pairs that would be applied to text."""
        aliases = self.get_all_aliases()
        result = {}
        sorted_aliases = sorted(aliases.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            word = aliases[alias]
            if alias in text and alias != word:
                result[alias] = word
        return result


def load_glossary(path: Path, lang: str) -> HotwordGlossary:
    """Load canonical YAML or the former equals-format glossary."""
    if not path.exists():
        return HotwordGlossary(lang=lang)
    document = load_yaml_glossary(path)
    glossary = HotwordGlossary(lang=lang, document=document)
    for term in document.terms:
        glossary.add(Hotword(word=term.canonical, aliases=list(term.aliases)))
    return glossary


def save_glossary(glossary: HotwordGlossary, path: Path) -> None:
    """Save hotword terms into the canonical YAML document."""
    document = glossary._document.model_copy(deep=True)
    document.terms = [
        GlossaryTerm(canonical=hotword.word, aliases=hotword.aliases)
        for hotword in glossary.hotwords
    ]
    save_yaml_glossary(path, document)
    glossary._document = document
