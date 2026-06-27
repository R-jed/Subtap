"""Setup wizard business logic."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DOWNLOAD_SOURCES = ("hf", "hf-mirror", "modelscope", "manual")


class SetupWizard:
    """User-level setup wizard for Subtap."""

    def check_system_deps(self) -> dict[str, bool]:
        """Check system dependencies.

        Returns:
            Dict mapping dependency name to availability status.
        """
        return {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None,
            "python": sys.version_info >= (3, 10),
        }

    def check_config_exists(self) -> bool:
        """Check if ~/.subtap/config.yaml exists."""
        config_path = Path.home() / ".subtap" / "config.yaml"
        return config_path.exists()

    def run_init(self) -> bool:
        """Run init command internally.

        Returns:
            True if init succeeded, False otherwise.
        """
        from subtap.cli import init
        try:
            init()
            return True
        except Exception as e:
            logger.error("初始化失败: %s", e)
            return False

    def choose_download_source(self, requested: str = "ask") -> str:
        """Choose download source interactively or from parameter.

        Args:
            requested: One of DOWNLOAD_SOURCES or "ask".

        Returns:
            Selected download source string.
        """
        if requested in DOWNLOAD_SOURCES:
            return requested
        if requested != "ask":
            raise ValueError(f"未知下载方式：{requested}")

        import typer

        typer.echo("请选择模型安装方式：")
        typer.echo("  1. Hugging Face 直连")
        typer.echo("  2. Hugging Face 国内镜像（https://hf-mirror.com）")
        typer.echo("  3. ModelScope")
        typer.echo("  4. 手动放入 models/")
        choice = typer.prompt("输入序号", default="1")
        return {"1": "hf", "2": "hf-mirror", "3": "modelscope", "4": "manual"}.get(choice, "hf")

    def setup_models(self, source: str = "ask", include_optional: bool = False, endpoint: str | None = None) -> bool:
        """Setup models with download source selection.

        Args:
            source: Download source (hf / hf-mirror / modelscope / manual / ask)
            include_optional: Also download optional larger models
            endpoint: Custom Hugging Face mirror endpoint

        Returns:
            True if all required models downloaded successfully.
        """
        from subtap.schemas.config import load_config
        from subtap.core.models import ModelDownloader

        config = load_config(Path.home() / ".subtap" / "config.yaml")
        if endpoint:
            config.models.hf_mirror_endpoint = endpoint
        downloader = ModelDownloader(config)
        selected = self.choose_download_source(source)
        if selected == "manual":
            self.print_manual_model_instructions()
            return False

        targets = ["asr_0.6b", "aligner"]
        if include_optional:
            targets.append("asr_1.7b")
        results = [self._download_model(downloader, name, selected) for name in targets]
        return all(results)

    def print_manual_model_instructions(self) -> None:
        """Print instructions for manual model placement."""
        import typer
        typer.echo("请手动下载模型并放入 models/ 目录：")
        typer.echo("  - asr_0.6b/models/asr_0.6b/")
        typer.echo("  - asr_1.7b/models/asr_1.7b/")
        typer.echo("  - aligner/models/aligner/")

    def _download_model(self, downloader, model_name: str, source: str = "hf") -> bool:
        """Download a single model.

        Args:
            downloader: ModelDownloader instance
            model_name: Name of model to download
            source: Download source

        Returns:
            True if download succeeded.
        """
        try:
            downloader.download(model_name, source=source)
            return True
        except NotImplementedError:
            logger.warning("模型 %s 下载未实现", model_name)
            return False
        except Exception as e:
            logger.warning("模型 %s 下载失败: %s", model_name, e)
            return False
