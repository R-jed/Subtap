"""Manuscript index: JSON-backed tracking of user reference documents."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ManuscriptIndex:
    """Track manuscript metadata in a JSON index file.

    Each entry stores: name, path, added_time, recent_use_time.
    The ``exists`` field is computed on every ``list_all()`` call.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._data: list[dict[str, Any]] = []
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_index(self, name: str) -> int:
        for i, entry in enumerate(self._data):
            if entry["name"] == name:
                return i
        return -1

    def add(self, name: str, file_path: str) -> None:
        """Add or overwrite a manuscript entry."""
        now = datetime.now(timezone.utc).isoformat()
        idx = self._find_index(name)
        entry: dict[str, Any] = {
            "name": name,
            "path": file_path,
            "added_time": now,
            "recent_use_time": None,
        }
        if idx >= 0:
            # Preserve original added_time on overwrite
            entry["added_time"] = self._data[idx].get("added_time", now)
            self._data[idx] = entry
        else:
            self._data.append(entry)
        self._save()

    def remove(self, name: str) -> bool:
        """Remove a manuscript by name. Returns False if not found."""
        idx = self._find_index(name)
        if idx < 0:
            return False
        self._data.pop(idx)
        self._save()
        return True

    def touch(self, name: str) -> None:
        """Update recent_use_time for a manuscript. Raises KeyError if not found."""
        idx = self._find_index(name)
        if idx < 0:
            raise KeyError(name)
        self._data[idx]["recent_use_time"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def list_all(self) -> list[dict[str, Any]]:
        """List all manuscripts with an ``exists`` field indicating file presence."""
        result: list[dict[str, Any]] = []
        for entry in self._data:
            item = dict(entry)
            item["exists"] = Path(entry["path"]).exists()
            result.append(item)
        return result
