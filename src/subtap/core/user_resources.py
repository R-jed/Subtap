"""Paths and initialization for user-owned Subtap resources."""

from __future__ import annotations

from pathlib import Path


def default_glossary_path(subtap_root: Path | None = None) -> Path:
    """Return the canonical default glossary path."""
    root = subtap_root or Path.home() / ".subtap"
    return root / "glossaries" / "default.yaml"


def ensure_default_glossary(subtap_root: Path | None = None) -> Path:
    """Create the empty default glossary once without overwriting user data."""
    path = default_glossary_path(subtap_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return path
