"""Workspace hygiene checks before pipeline execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Files that are safe to clean (temp/cache)
_CLEANABLE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "thumbs.db",
    "desktop.ini",
}

# Directories whose entire contents are temp intermediates
_CLEANABLE_DIRS = {"__pycache__"}

# Chunk wav files are temp intermediates (not user output)
_CHUNK_WAV_GLOB = "chunks/chunk_*.wav"


class Cleanroom:
    """Workspace hygiene checker and cleaner.

    Rules:
    - Never delete user output (SRT, JSON, aligned.jsonl, etc.)
    - Only clean temporary intermediate cache files
    - Fix corrupt event logs
    """

    def __init__(self, workspace_root: Path):
        self.root = workspace_root

    def check_workspace(self) -> dict[str, Any]:
        """Check workspace state without modifying anything.

        Returns:
            {"is_clean": bool, "issues": list[str]}
        """
        issues: list[str] = []

        # Check for temp/cache files
        for name in _CLEANABLE_NAMES:
            for f in self.root.rglob(name):
                issues.append(f"临时文件: {f.relative_to(self.root)}")

        # Check for chunk wav files
        for f in self.root.glob(_CHUNK_WAV_GLOB):
            issues.append(f"临时缓存: {f.relative_to(self.root)}")

        # Check for corrupt event log
        log_path = self.root / "logs" / "event.log.jsonl"
        if log_path.exists():
            try:
                for line in log_path.read_text().strip().splitlines():
                    if line.strip():
                        json.loads(line)
            except (json.JSONDecodeError, ValueError):
                issues.append("event.log.jsonl 包含无效 JSON 行")

        return {"is_clean": len(issues) == 0, "issues": issues}

    def clean_workspace(self) -> dict[str, Any]:
        """Remove temp files and fix corrupt logs.

        Never removes user output (SRT, JSON in output/, aligned.jsonl, etc.)

        Returns:
            {"cleaned_count": int, "issues": list[str], "is_clean": bool}
        """
        cleaned = 0
        issues: list[str] = []

        # Remove temp/cache files
        for name in _CLEANABLE_NAMES:
            for f in self.root.rglob(name):
                if f.is_file():
                    f.unlink()
                    cleaned += 1

        # Remove chunk wav files (temp intermediates)
        for f in self.root.glob(_CHUNK_WAV_GLOB):
            if f.is_file():
                f.unlink()
                cleaned += 1

        # Remove __pycache__ directories
        for d in self.root.rglob("__pycache__"):
            if d.is_dir():
                import shutil

                shutil.rmtree(d)
                cleaned += 1

        # Fix corrupt event log
        log_path = self.root / "logs" / "event.log.jsonl"
        if log_path.exists():
            try:
                for line in log_path.read_text().strip().splitlines():
                    if line.strip():
                        json.loads(line)  # validate
            except (json.JSONDecodeError, ValueError):
                # Remove corrupt log entirely
                log_path.unlink()
                cleaned += 1
                issues.append("已清理损坏的 event.log.jsonl")

        return {
            "cleaned_count": cleaned,
            "issues": issues,
            "is_clean": len(issues) == 0,
        }

    def check_model_status(self) -> dict[str, Any]:
        """Report model availability.

        Returns:
            {"models": [{"name": str, "installed": bool, "path": str}, ...]}
        """
        project_root = self.root.parent  # work/ is inside project root
        models_dir = project_root / "models"
        model_names = ["asr_0.6b", "asr_1.7b", "aligner"]

        models = []
        for name in model_names:
            model_path = models_dir / name
            installed = (
                model_path.exists() and any(model_path.iterdir())
                if model_path.exists()
                else False
            )
            models.append(
                {
                    "name": name,
                    "installed": installed,
                    "path": str(model_path),
                }
            )

        return {"models": models}
