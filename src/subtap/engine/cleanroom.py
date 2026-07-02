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

    # ---- 分层清理 ----

    # L1 临时文件：chunk WAV、source WAV、系统文件、__pycache__
    _L1_SYSTEM_NAMES = _CLEANABLE_NAMES
    _L1_SYSTEM_DIRS = _CLEANABLE_DIRS

    # L2 中间文件：asr.jsonl、asr_draft.jsonl、cleaned.jsonl、sentences.jsonl
    _L2_INTERMEDIATE_FILES = [
        "asr/asr.jsonl",
        "asr/asr_draft.jsonl",
        "cleaned.jsonl",
        "sentences.jsonl",
    ]

    # 永远不清理的文件/目录
    _PROTECTED_FILES = [
        "aligned.jsonl",
        "metrics.json",
    ]
    _PROTECTED_DIRS = ["output"]

    def clean_temp_files(self, exclude_chunks: bool = False) -> dict[str, Any]:
        """清理 L1 临时文件。

        Args:
            exclude_chunks: 为 True 时保留 chunk WAV 文件。

        Returns:
            {"cleaned_count": int, "cleaned_files": list[str]}
        """
        cleaned_files: list[str] = []

        # chunk WAV 文件
        if not exclude_chunks:
            for f in self.root.glob(_CHUNK_WAV_GLOB):
                if f.is_file():
                    cleaned_files.append(str(f.relative_to(self.root)))
                    f.unlink()

        # source WAV
        source = self.root / "audio" / "source.wav"
        if source.is_file():
            cleaned_files.append(str(source.relative_to(self.root)))
            source.unlink()

        # 系统文件
        for name in self._L1_SYSTEM_NAMES:
            for f in self.root.rglob(name):
                if f.is_file():
                    cleaned_files.append(str(f.relative_to(self.root)))
                    f.unlink()

        # __pycache__
        for d in self.root.rglob("__pycache__"):
            if d.is_dir():
                import shutil

                shutil.rmtree(d)
                cleaned_files.append(str(d.relative_to(self.root)))

        return {
            "cleaned_count": len(cleaned_files),
            "cleaned_files": cleaned_files,
        }

    def clean_intermediate_files(self) -> dict[str, Any]:
        """清理 L2 中间文件。

        永远不删除：aligned.jsonl、metrics.json、output/

        Returns:
            {"cleaned_count": int, "cleaned_files": list[str]}
        """
        cleaned_files: list[str] = []

        for rel_path in self._L2_INTERMEDIATE_FILES:
            f = self.root / rel_path
            if f.is_file():
                cleaned_files.append(rel_path)
                f.unlink()

        return {
            "cleaned_count": len(cleaned_files),
            "cleaned_files": cleaned_files,
        }

    def clean_all(self) -> dict[str, Any]:
        """清理所有临时和中间文件（L1 + L2）。

        永远不删除：aligned.jsonl、metrics.json、output/

        Returns:
            {"cleaned_count": int, "cleaned_files": list[str]}
        """
        l1 = self.clean_temp_files()
        l2 = self.clean_intermediate_files()
        return {
            "cleaned_count": l1["cleaned_count"] + l2["cleaned_count"],
            "cleaned_files": l1["cleaned_files"] + l2["cleaned_files"],
        }

    def format_summary(self, result: dict[str, Any]) -> str:
        """格式化清理结果摘要。

        Returns:
            人类可读的清理摘要字符串。
        """
        count = result.get("cleaned_count", 0)
        files = result.get("cleaned_files", [])
        issues = result.get("issues", [])

        lines: list[str] = []
        if count == 0:
            lines.append("工作区无需清理，已是干净状态。")
        else:
            lines.append(f"已清理 {count} 个文件/目录：")
            for f in files:
                lines.append(f"  - {f}")

        if issues:
            lines.append("问题：")
            for issue in issues:
                lines.append(f"  - {issue}")

        return "\n".join(lines)

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
