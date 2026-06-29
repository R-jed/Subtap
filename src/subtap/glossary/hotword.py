"""Hotword glossary management — TSV format, per-language."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Hotword:
    """A single hotword entry."""

    word: str
    aliases: list[str] = field(default_factory=list)
    pronunciation: str = ""

    def to_tsv_row(self) -> str:
        """Convert to TSV row.

        Format: word\talias1\talias2\talias3\tpronunciation
        """
        # Pad aliases to exactly 3 columns
        padded_aliases = (self.aliases + [""] * 3)[:3]
        parts = [self.word] + padded_aliases
        if self.pronunciation:
            parts.append(self.pronunciation)
        return "\t".join(parts)

    @classmethod
    def from_tsv_row(cls, row: str) -> Hotword:
        """Parse from TSV row.

        Format: word\talias1\talias2\talias3\tpronunciation
        """
        parts = row.strip().split("\t")
        if not parts:
            return cls(word="")
        word = parts[0]
        # aliases are columns 1-3, pronunciation is column 4 (if exists)
        aliases = [a.strip() for a in parts[1:4] if a.strip()]
        pronunciation = parts[4].strip() if len(parts) > 4 else ""
        return cls(word=word, aliases=aliases, pronunciation=pronunciation)


class HotwordGlossary:
    """Hotword glossary for a specific language."""

    def __init__(self, lang: str, hotwords: list[Hotword] | None = None):
        self.lang = lang
        self.hotwords: list[Hotword] = hotwords or []

    def add(self, hotword: Hotword) -> None:
        """Add a hotword."""
        self.hotwords.append(hotword)

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


def load_glossary(path: Path, lang: str) -> HotwordGlossary:
    """Load glossary from TSV file."""
    glossary = HotwordGlossary(lang=lang)
    if not path.exists():
        return glossary
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("热词") or line.startswith("word"):
                continue
            hw = Hotword.from_tsv_row(line)
            if hw.word:
                glossary.add(hw)
    except Exception:
        pass
    return glossary


def save_glossary(glossary: HotwordGlossary, path: Path) -> None:
    """Save glossary to TSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["热词\t错词1\t错词2\t错词3"]
    for hw in glossary.hotwords:
        lines.append(hw.to_tsv_row())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
