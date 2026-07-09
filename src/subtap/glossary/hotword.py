"""Hotword glossary management — equals format, per-language.

Format (one row per hotword):
    热词=错词1,错词2,错词3
    理光GR4=李光机亚四,理光GR IV,理光GRIV
    GR=吉亚斯,吉奥,吉亚
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Hotword:
    """A single hotword entry."""

    word: str
    aliases: list[str] = field(default_factory=list)


class HotwordGlossary:
    """Hotword glossary for a specific language."""

    def __init__(self, lang: str, hotwords: list[Hotword] | None = None):
        self.lang = lang
        self.hotwords: list[Hotword] = hotwords or []

    def add(self, hotword: Hotword) -> None:
        """Add a hotword."""
        self.hotwords.append(hotword)

    def add_alias(self, word: str, alias: str) -> None:
        """Add an alias to existing hotword or create new one."""
        for hw in self.hotwords:
            if hw.word == word:
                if alias not in hw.aliases:
                    hw.aliases.append(alias)
                return
        self.hotwords.append(Hotword(word=word, aliases=[alias]))

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
    """Load glossary from equals format file.

    Format: 热词=错词1,错词2,错词3
    """
    glossary = HotwordGlossary(lang=lang)
    if not path.exists():
        return glossary
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            parts = line.split("=", 1)
            if len(parts) == 2:
                word = parts[0].strip()
                aliases_str = parts[1].strip()
                if word and aliases_str:
                    aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
                    for alias in aliases:
                        glossary.add_alias(word, alias)
    except Exception as e:
        logger.warning("Failed to load glossary from %s: %s", path, e)
    return glossary


def save_glossary(glossary: HotwordGlossary, path: Path) -> None:
    """Save glossary to equals format file.

    Format: 热词=错词1,错词2,错词3
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for hw in glossary.hotwords:
        if hw.aliases:
            aliases_str = ",".join(hw.aliases)
            lines.append(f"{hw.word}={aliases_str}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
