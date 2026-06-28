"""Editable YAML profile store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ProfileStore:
    """Read and write the local user learning profile."""

    FILES = {
        "glossary": "glossary.yaml",
        "corrections": "corrections.yaml",
        "segmentation_preferences": "segmentation_preferences.yaml",
        "translation_terms": "translation_terms.yaml",
    }

    def __init__(self, root: Path | None = None):
        self.root = root or Path.home() / ".subtap" / "profile"
        self.root.mkdir(parents=True, exist_ok=True)
        self.ensure_files()

    def ensure_files(self) -> None:
        defaults: dict[str, dict[str, Any]] = {
            "glossary": {"replacements": []},
            "corrections": {"pairs": []},
            "segmentation_preferences": {"patterns": []},
            "translation_terms": {"terms": []},
        }
        for key, filename in self.FILES.items():
            path = self.root / filename
            if not path.exists():
                self._write(path, defaults[key])

    def _read(self, filename: str) -> dict[str, Any]:
        path = self.root / filename
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def add_glossary_replacement(self, find: str, replace: str) -> None:
        path = self.root / self.FILES["glossary"]
        payload = self._read(self.FILES["glossary"])
        replacements = payload.setdefault("replacements", [])
        replacements.append({"find": find, "replace": replace})
        self._write(path, payload)

    def list_glossary_replacements(self) -> list[dict[str, str]]:
        payload = self._read(self.FILES["glossary"])
        return payload.get("replacements", [])

    def remove_glossary_replacement(self, find: str) -> bool:
        path = self.root / self.FILES["glossary"]
        payload = self._read(self.FILES["glossary"])
        before = list(payload.get("replacements", []))
        payload["replacements"] = [item for item in before if item.get("find") != find]
        self._write(path, payload)
        return len(payload["replacements"]) != len(before)

    def apply_corrections(
        self,
        pairs: list[dict[str, str]],
        *,
        confirmed: bool,
    ) -> bool:
        if not confirmed:
            return False
        path = self.root / self.FILES["corrections"]
        payload = self._read(self.FILES["corrections"])
        payload.setdefault("pairs", []).extend(pairs)
        self._write(path, payload)
        return True

    def list_corrections(self) -> list[dict[str, str]]:
        payload = self._read(self.FILES["corrections"])
        return payload.get("pairs", [])

    def export(self, output_path: Path) -> Path:
        payload = {key: self._read(filename) for key, filename in self.FILES.items()}
        self._write(output_path, payload)
        return output_path
