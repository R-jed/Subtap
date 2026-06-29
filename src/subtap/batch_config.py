"""Batch config management — YAML config file for batch transcription."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_CONFIG = {
    "mode": "fast",
    "enhance": "local",
    "translate_to": None,
    "bilingual": "off",
    "max_chars": 25,
    "min_chars": 10,
    "punctuation": False,
    "subtitle_language": "zh",
}


@dataclass
class BatchConfig:
    """Batch transcription configuration."""

    mode: str = "fast"
    enhance: str = "local"
    translate_to: str | None = None
    bilingual: str = "off"
    max_chars: int = 25
    min_chars: int = 10
    punctuation: bool = False
    subtitle_language: str = "zh"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatchConfig:
        """Create config from dictionary, using defaults for missing keys."""
        merged = {**DEFAULT_CONFIG, **data}
        return cls(
            mode=merged["mode"],
            enhance=merged["enhance"],
            translate_to=merged["translate_to"],
            bilingual=merged["bilingual"],
            max_chars=merged["max_chars"],
            min_chars=merged["min_chars"],
            punctuation=merged["punctuation"],
            subtitle_language=merged["subtitle_language"],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "mode": self.mode,
            "enhance": self.enhance,
            "translate_to": self.translate_to,
            "bilingual": self.bilingual,
            "max_chars": self.max_chars,
            "min_chars": self.min_chars,
            "punctuation": self.punctuation,
            "subtitle_language": self.subtitle_language,
        }


def load_batch_config(path: Path) -> BatchConfig:
    """Load batch config from YAML file."""
    if not path.exists():
        return BatchConfig()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return BatchConfig()
        return BatchConfig.from_dict(data)
    except Exception:
        return BatchConfig()


def save_batch_config(config: BatchConfig, path: Path) -> None:
    """Save batch config to YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(config.to_dict(), allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
