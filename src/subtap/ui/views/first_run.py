"""First-run initialization wizard."""

from __future__ import annotations

import shutil
import importlib.util
import os
import math
from pathlib import Path


class FirstRunView:
    """7-step initialization wizard for first launch."""

    def check_device(self) -> dict:
        """Check device capabilities."""
        import platform

        is_arm64 = platform.machine() == "arm64"
        is_darwin = platform.system() == "Darwin"
        has_ffmpeg = shutil.which("ffmpeg") is not None
        has_mlx = (
            importlib.util.find_spec("mlx") is not None
            and importlib.util.find_spec("mlx_audio") is not None
        )

        try:
            memory_gb = (
                os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024**3)
            )
        except (ValueError, OSError):
            memory_gb = 0

        # Check disk space
        try:
            usage = shutil.disk_usage(Path.home())
            free_gb = usage.free / (1024**3)
        except Exception:
            free_gb = 0

        return {
            "is_apple_silicon": is_arm64 and is_darwin,
            "has_ffmpeg": has_ffmpeg,
            "has_mlx": has_mlx,
            "memory_gb": memory_gb,
            "free_gb": free_gb,
        }

    def recommend_model(self, fast_ok: bool, quality_ok: bool) -> str:
        """Recommend model based on device capabilities."""
        if quality_ok:
            return "asr_1.7b"
        if fast_ok:
            return "asr_0.6b"
        raise ValueError(
            "设备不满足任何模型运行条件（fast_ok 和 quality_ok 均为 False）"
        )

    def get_download_info(
        self, model_name: str, *, manifest_path: Path | None = None
    ) -> dict:
        """Get download size and estimated time for a model."""
        from subtap.core.manifest import get_manifest_path, load_manifest

        path = manifest_path or get_manifest_path(None)
        manifest = load_manifest(path)
        try:
            entry = manifest.models[model_name]
        except KeyError as exc:
            raise ValueError(f"未知模型：{model_name}") from exc
        size = sum(file.size_bytes for file in entry.required_files)
        if size <= 0:
            size = entry.min_disk_bytes
        return {
            "model_name": model_name,
            "size_bytes": size,
            "size_display": f"{size / (1024**3):.1f} GB",
            "estimated_seconds": math.ceil(size / (10 * 1024 * 1024)),
            "target_dir": str(Path.home() / ".subtap" / "models"),
        }

    def run_offline_self_check(self, config, model_name: str) -> None:
        """Verify the downloaded model is complete before finishing setup."""
        from subtap.core.models import ModelVerifier

        result = ModelVerifier(config).verify(model_name, require_hash=True)
        if result["status"] != "ok":
            raise RuntimeError(
                f"离线自检失败：模型 {model_name} 状态为 {result['status']}"
            )

    @staticmethod
    def failure_actions() -> tuple[str, str, str]:
        return ("重试", "切换下载源", "查看详情")

    def mark_complete(self) -> Path:
        """Return the state file path for marking first-run complete.

        The caller is responsible for creating StateStore and calling load().
        """
        return Path.home() / ".subtap" / "state.json"
