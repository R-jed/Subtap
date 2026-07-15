"""First-run initialization wizard."""

from __future__ import annotations

import shutil
import importlib.util
import os
import math
from pathlib import Path

from subtap.schemas.config import SubtapConfig


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
        plan = self.get_download_plan((model_name,), manifest_path=manifest_path)
        return {**plan, "model_name": model_name}

    def get_download_plan(
        self,
        model_names: tuple[str, ...],
        *,
        manifest_path: Path | None = None,
        config: SubtapConfig | None = None,
        cancelled=None,
    ) -> dict:
        """Get total and remaining download sizes for an offline runtime."""
        from subtap.core.manifest import get_manifest_path, load_manifest
        from subtap.core.models import ModelRegistry, verify_file_sha256

        path = manifest_path or get_manifest_path(config)
        manifest = load_manifest(path)
        model_root = (
            ModelRegistry(config).root
            if config is not None
            else Path.home() / ".subtap" / "models"
        )
        size = 0
        download_bytes = 0
        existing_bytes_by_file: dict[tuple[str, str], int] = {}
        verified_files: set[tuple[str, str]] = set()
        try:
            for model_name in model_names:
                model = manifest.models[model_name]
                declared_size = sum(file.size_bytes for file in model.required_files)
                model_size = declared_size or model.min_disk_bytes
                size += model_size
                if config is None or not declared_size:
                    download_bytes += model_size
                    continue
                for file in model.required_files:
                    expected = file.size_bytes
                    path = model_root / model.subdir / file.name
                    existing = (
                        min(path.stat().st_size, expected) if path.exists() else 0
                    )
                    if expected > 0 and existing == expected:
                        if file.sha256 and verify_file_sha256(
                            path, file.sha256, cancelled=cancelled
                        ):
                            verified_files.add((model_name, file.name))
                        else:
                            existing = 0
                    if existing:
                        existing_bytes_by_file[(model_name, file.name)] = existing
                    download_bytes += expected - existing
        except KeyError as e:
            raise ValueError(f"未知模型：{e.args[0]}") from e
        return {
            "model_names": model_names,
            "size_bytes": size,
            "download_bytes": download_bytes,
            "existing_bytes_by_file": existing_bytes_by_file,
            "verified_files": verified_files,
            "size_display": f"{size / (1024**3):.1f} GB",
            "estimated_seconds": math.ceil(download_bytes / (10 * 1024 * 1024)),
            "target_dir": str(model_root),
        }

    def download_required_models(
        self,
        config,
        *,
        source: str,
        progress=None,
        cancelled=None,
        verified_files: set[tuple[str, str]] | None = None,
    ) -> None:
        """Download missing runtime models while preserving verified completed ones."""
        from subtap.core.models import (
            DownloadCancelled,
            ModelDownloader,
            ModelVerifier,
            required_model_names,
        )

        downloader = ModelDownloader(config)
        verifier = ModelVerifier(config)
        for model_name in required_model_names(config):
            if verified_files is None and (
                verifier.verify(model_name, require_hash=True, cancelled=cancelled)[
                    "status"
                ]
                == "ok"
            ):
                continue

            def on_progress(filename, downloaded, total, *, _model=model_name):
                if cancelled is not None and cancelled():
                    raise DownloadCancelled("模型下载已取消，可稍后继续")
                if progress is not None:
                    progress(_model, filename, downloaded, total)

            downloader.download(
                model_name,
                source=source,
                progress=on_progress,
                cancelled=cancelled,
                verified_files={
                    filename
                    for verified_model, filename in (verified_files or set())
                    if verified_model == model_name
                },
            )

    def run_offline_self_check(
        self, config, model_name: str, *, cancelled=None
    ) -> None:
        """Verify the downloaded model is complete before finishing setup."""
        from subtap.core.models import ModelVerifier

        result = ModelVerifier(config).verify(
            model_name, require_hash=True, cancelled=cancelled
        )
        if result["status"] != "ok":
            raise RuntimeError(
                f"离线自检失败：模型 {model_name} 状态为 {result['status']}"
            )

    def run_required_offline_self_check(self, config, *, cancelled=None) -> None:
        """Verify every model required by the selected offline runtime."""
        from subtap.core.models import required_model_names

        for model_name in required_model_names(config):
            self.run_offline_self_check(config, model_name, cancelled=cancelled)

    @staticmethod
    def failure_actions() -> tuple[str, str, str]:
        return ("重试", "切换下载源", "查看详情")

    def mark_complete(self) -> Path:
        """Return the state file path for marking first-run complete.

        The caller is responsible for creating StateStore and calling load().
        """
        return Path.home() / ".subtap" / "state.json"
