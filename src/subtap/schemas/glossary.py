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
        term_replacements = [
            (alias, term.canonical)
            for term in self.terms
            for alias in term.aliases
            if alias and alias != term.canonical
        ]
        return term_replacements + [(r.find, r.replace) for r in self.replacements]

    def upsert_term(self, term: GlossaryTerm) -> None:
        """Add a canonical term or merge new aliases into the existing term."""
        existing = next(
            (item for item in self.terms if item.canonical == term.canonical),
            None,
        )
        if existing is None:
            self.terms.append(term)
        else:
            existing.aliases.extend(
                alias for alias in term.aliases if alias not in existing.aliases
            )
        self.model_post_init(None)

    def remove_entry(self, value: str) -> bool:
        """Remove a canonical term, alias, or direct replacement by its source."""
        before = self.model_dump()
        self.terms = [item for item in self.terms if item.canonical != value]
        for term in self.terms:
            term.aliases = [alias for alias in term.aliases if alias != value]
        self.replacements = [item for item in self.replacements if item.find != value]
        changed = self.model_dump() != before
        if changed:
            self.model_post_init(None)
        return changed


def _load_legacy_equals(content: str) -> Glossary:
    """Load the former ``canonical=alias1,alias2`` hotword format."""
    terms: list[GlossaryTerm] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("术语表格式无效：应为 YAML 或 术语=别名1,别名2")
        canonical, aliases_text = [part.strip() for part in line.split("=", 1)]
        aliases = [item.strip() for item in aliases_text.split(",") if item.strip()]
        if not canonical or not aliases:
            raise ValueError("术语表格式无效：术语和别名不能为空")
        terms.append(GlossaryTerm(canonical=canonical, aliases=aliases))
    return Glossary(terms=terms)


def load_glossary(path: Optional[Path]) -> Glossary:
    """Load glossary from YAML file.

    Returns empty Glossary if path is None or file doesn't exist.
    """
    if path is None or not path.exists():
        return Glossary()

    content = path.read_text(encoding="utf-8")

    if not content.strip():
        return Glossary()

    result = yaml.safe_load(content)
    if isinstance(result, str) and "=" in content:
        return _load_legacy_equals(content)
    if not isinstance(result, dict):
        raise ValueError("术语表格式无效：根节点必须是 YAML 对象")
    return Glossary.model_validate(result)


def save_glossary(path: Path, glossary: Glossary) -> None:
    """Persist the canonical YAML glossary without dropping any sections."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = glossary.model_dump(mode="json")
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
