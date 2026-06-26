"""Glossary loader and data model.

Supports YAML glossary files with:
- terms: canonical → list of aliases (alias → canonical mapping)
- replacements: direct string replacements (case-insensitive)
- style: style rules passed to LLM
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
    """A canonical term with optional aliases."""

    canonical: str
    aliases: list[str] = Field(default_factory=list)


class GlossaryReplacement(BaseModel):
    """A deterministic string replacement rule."""

    find: str
    replace: str


class Glossary(BaseModel):
    """Loaded glossary with normalized lookup structures."""

    terms: list[GlossaryTerm] = Field(default_factory=list)
    replacements: list[GlossaryReplacement] = Field(default_factory=list)
    style: list[str] = Field(default_factory=list)

    # Internal normalized maps (built on load)
    _alias_map: dict[str, str] = {}

    def model_post_init(self, __context: object) -> None:
        """Build case-insensitive alias → canonical map."""
        self._alias_map = {}
        for term in self.terms:
            key = term.canonical.lower()
            self._alias_map[key] = term.canonical
            for alias in term.aliases:
                self._alias_map[alias.lower()] = term.canonical

    def resolve_alias(self, text: str) -> str:
        """Resolve a term to its canonical form (case-insensitive)."""
        return self._alias_map.get(text.lower(), text)

    def get_replacements(self) -> list[tuple[str, str]]:
        """Return (find, replace) pairs for deterministic replacement."""
        return [(r.find, r.replace) for r in self.replacements]


def load_glossary(path: Optional[Path]) -> Glossary:
    """Load glossary from YAML file.

    Returns empty Glossary if path is None or file doesn't exist.
    """
    if path is None or not path.exists():
        return Glossary()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return Glossary.model_validate(data)
