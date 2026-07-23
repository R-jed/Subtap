"""Glossary loader and data model.

Supports YAML glossary files with:
- terms: canonical → list of aliases (alias → canonical mapping)
- replacements: direct string replacements (case-insensitive)
- style: style rules passed to LLM
"""

from __future__ import annotations

from pathlib import Path
import re
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
        aliases: list[str] = []
        alias_keys: set[str] = set()
        for alias in term.aliases:
            key = alias.lower()
            if key != term.canonical.lower() and key not in alias_keys:
                aliases.append(alias)
                alias_keys.add(key)
        term.aliases = aliases
        canonical_key = term.canonical.lower()
        existing = next(
            (item for item in self.terms if item.canonical.lower() == canonical_key),
            None,
        )
        conflict = next(
            (item for item in self.terms if item.canonical.lower() in alias_keys),
            None,
        )
        if conflict is not None:
            raise ValueError(f"别名不能与已有标准词相同：{conflict.canonical}")
        for item in self.terms:
            if item is not existing:
                item.aliases = [
                    alias for alias in item.aliases if alias.lower() not in alias_keys
                ]
        if existing is None:
            self.terms.append(term)
        else:
            existing_aliases = {alias.lower() for alias in existing.aliases}
            existing.aliases.extend(
                alias for alias in term.aliases if alias.lower() not in existing_aliases
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


def _parse_plain_glossary(
    content: str,
) -> tuple[Glossary, list[tuple[int, str, list[str]]]]:
    """Parse the user-facing one-entry-per-line glossary format."""
    terms: list[GlossaryTerm] = []
    entries: list[tuple[int, str, list[str]]] = []
    errors: list[str] = []
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        separators = list(re.finditer(r"[=＝]", line))
        if len(separators) > 1:
            errors.append(f"第 {line_number} 行：只能使用一个等号")
            continue
        if not separators:
            if re.search(r"[,，]", line):
                errors.append(f"第 {line_number} 行：逗号只能用于等号右侧的错写列表")
                continue
            canonical = line
            aliases: list[str] = []
        else:
            separator = separators[0]
            canonical = line[: separator.start()].strip()
            aliases_text = line[separator.end() :].strip()
            alias_parts = re.split(r"[,，]", aliases_text)
            aliases = [item.strip() for item in alias_parts]
            if not canonical or not aliases_text or any(not item for item in aliases):
                errors.append(f"第 {line_number} 行：正确写法和错写均不能为空")
                continue
        terms.append(GlossaryTerm(canonical=canonical, aliases=aliases))
        entries.append((line_number, canonical, aliases))

    canonical_lines: dict[str, int] = {}
    alias_lines: dict[str, tuple[str, int]] = {}
    for line_number, canonical, aliases in entries:
        canonical_key = canonical.casefold()
        previous_line = canonical_lines.get(canonical_key)
        if previous_line is not None:
            errors.append(
                f'第 {line_number} 行：正确写法 "{canonical}" '
                f"与第 {previous_line} 行重复"
            )
        else:
            canonical_lines[canonical_key] = line_number

        aliases_on_line: set[str] = set()
        for alias in aliases:
            alias_key = alias.casefold()
            if alias_key == canonical_key:
                errors.append(f'第 {line_number} 行：错写 "{alias}" 与正确写法相同')
            if alias_key in aliases_on_line:
                errors.append(f'第 {line_number} 行：错写 "{alias}" 重复')
            aliases_on_line.add(alias_key)

    for line_number, canonical, aliases in entries:
        for alias in aliases:
            alias_key = alias.casefold()
            canonical_line = canonical_lines.get(alias_key)
            if canonical_line is not None:
                errors.append(
                    f'第 {line_number} 行：错写 "{alias}" '
                    f"与第 {canonical_line} 行的正确写法冲突"
                )
            previous = alias_lines.get(alias_key)
            if previous is not None and previous[0].casefold() != canonical.casefold():
                errors.append(
                    f'第 {line_number} 行：错写 "{alias}" '
                    f"已在第 {previous[1]} 行映射到另一正确写法"
                )
            else:
                alias_lines[alias_key] = (canonical, line_number)

    if errors:
        raise ValueError("术语表格式无效：\n" + "\n".join(errors))
    return Glossary(terms=terms), entries


def _format_plain_term(term: GlossaryTerm) -> str:
    if not term.aliases:
        return term.canonical
    return f"{term.canonical} = {', '.join(term.aliases)}"


def _read_plain_text(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), has_bom


def _write_plain_text(path: Path, content: str, has_bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "\ufeff" if has_bom else ""
    path.write_text(prefix + content, encoding="utf-8")


def upsert_plain_glossary_terms(path: Path, terms: list[GlossaryTerm]) -> None:
    """Update only target entries while preserving the user's surrounding text."""
    if path.exists():
        content, has_bom = _read_plain_text(path)
    else:
        content, has_bom = "", False
    _, entries = _parse_plain_glossary(content)
    lines = content.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in content else "\n"

    for term in terms:
        match = next(
            (
                entry
                for entry in entries
                if entry[1].casefold() == term.canonical.casefold()
            ),
            None,
        )
        if match is None:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            lines.append(_format_plain_term(term) + newline)
        else:
            line_number, canonical, existing_aliases = match
            alias_keys = {alias.casefold() for alias in existing_aliases}
            aliases = list(existing_aliases)
            aliases.extend(
                alias for alias in term.aliases if alias.casefold() not in alias_keys
            )
            ending_match = re.search(r"(\r\n|\n|\r)$", lines[line_number - 1])
            ending = ending_match.group(1) if ending_match else ""
            lines[line_number - 1] = (
                _format_plain_term(GlossaryTerm(canonical=canonical, aliases=aliases))
                + ending
            )
        content = "".join(lines)
        _, entries = _parse_plain_glossary(content)

    _write_plain_text(path, content, has_bom)


def remove_plain_glossary_entry(path: Path, value: str) -> bool:
    """Delete only the line containing the requested canonical term or alias."""
    if not path.exists():
        return False
    content, has_bom = _read_plain_text(path)
    _, entries = _parse_plain_glossary(content)
    value_key = value.casefold()
    match = next(
        (
            entry
            for entry in entries
            if entry[1].casefold() == value_key
            or any(alias.casefold() == value_key for alias in entry[2])
        ),
        None,
    )
    if match is None:
        return False
    lines = content.splitlines(keepends=True)
    del lines[match[0] - 1]
    _write_plain_text(path, "".join(lines), has_bom)
    return True


def replace_plain_glossary_term(path: Path, term: GlossaryTerm) -> None:
    """Replace one term in place without disturbing surrounding user text."""
    content, has_bom = _read_plain_text(path)
    _, entries = _parse_plain_glossary(content)
    match = next(
        (
            entry
            for entry in entries
            if entry[1].casefold() == term.canonical.casefold()
        ),
        None,
    )
    if match is None:
        raise ValueError(f"未找到正确写法：{term.canonical}")
    lines = content.splitlines(keepends=True)
    ending_match = re.search(r"(\r\n|\n|\r)$", lines[match[0] - 1])
    ending = ending_match.group(1) if ending_match else ""
    lines[match[0] - 1] = _format_plain_term(term) + ending
    updated = "".join(lines)
    _parse_plain_glossary(updated)
    _write_plain_text(path, updated, has_bom)


def load_glossary(path: Optional[Path]) -> Glossary:
    """Load a plain-text or backward-compatible YAML glossary.

    Returns empty Glossary if path is None or file doesn't exist.
    """
    if path is None or not path.exists():
        return Glossary()

    content = path.read_text(encoding="utf-8-sig")

    if not content.strip():
        return Glossary()

    if path.suffix.lower() == ".txt":
        return _parse_plain_glossary(content)[0]

    result = yaml.safe_load(content)
    if isinstance(result, dict):
        return Glossary.model_validate(result)
    legacy_lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if legacy_lines and all(
        re.search(r"[=＝]", line) and not line.startswith(("-", "[", "{", "'", '"'))
        for line in legacy_lines
    ):
        return _parse_plain_glossary(content)[0]
    raise ValueError("术语表格式无效：根节点必须是 YAML 对象")


def save_glossary(path: Path, glossary: Glossary) -> None:
    """Persist a glossary in the format selected by its file extension."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".txt":
        if glossary.replacements or glossary.style:
            raise ValueError("纯文本热词表无法保存 replacements 或 style")
        content = "".join(f"{_format_plain_term(term)}\n" for term in glossary.terms)
        _write_plain_text(path, content)
        return
    data = glossary.model_dump(mode="json")
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
