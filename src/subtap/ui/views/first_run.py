"""First-run initialization wizard."""

from __future__ import annotations

import shutil
from pathlib import Path


class FirstRunView:
    """7-step initialization wizard for first launch."""

    def check_device(self) -> dict:
        """Check device capabilities."""
        import platform

        is_arm64 = platform.machine() == "arm64"
        is_darwin = platform.system() == "Darwin"
        has_ffmpeg = shutil.which("ffmpeg") is not None

        # Check disk space
        try:
            usage = shutil.disk_usage(Path.home())
            free_gb = usage.free / (1024**3)
        except Exception:
            free_gb = 0

        return {
            "is_apple_silicon": is_arm64 and is_darwin,
            "has_ffmpeg": has_ffmpeg,
            "free_gb": free_gb,
        }

    def recommend_model(self, fast_ok: bool, quality_ok: bool) -> str:
        """Recommend model based on device capabilities."""
        if quality_ok:
            return "asr_1.7b"
        if fast_ok:
            return "asr_0.6b"
        raise ValueError("设备不满足任何模型运行条件（fast_ok 和 quality_ok 均为 False）")

    def get_download_info(self, model_name: str) -> dict:
        """Get download size and estimated time for a model."""
        # Placeholder — real sizes from manifest
        sizes = {
            "asr_0.6b": 500_000_000,
            "asr_1.7b": 1_200_000_000,
            "aligner": 500_000_000,
        }
        size = sizes.get(model_name, 500_000_000)
        return {
            "model_name": model_name,
            "size_bytes": size,
            "size_display": f"{size / (1024**3):.1f} GB",
            "target_dir": str(Path.home() / ".subtap" / "models"),
        }

    def mark_complete(self) -> Path:
        """Return the state file path for marking first-run complete.

        The caller is responsible for creating StateStore and calling load().
        """
        return Path.home() / ".subtap" / "state.json"
