"""Setup wizard business logic."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DOWNLOAD_SOURCES = ("hf", "hf-mirror", "manual")


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
        typer.echo("  3. 手动放入 models/")
        choice = typer.prompt("输入序号", default="1")
        mapping = {"1": "hf", "2": "hf-mirror", "3": "manual"}
        if choice not in mapping:
            typer.echo(f"  无效选项 '{choice}'，默认使用 Hugging Face 直连")
        return mapping.get(choice, "hf")

    def setup_models(self, source: str = "ask", include_optional: bool = False, endpoint: str | None = None) -> bool:
        """Setup models with download source selection.

        Args:
            source: Download source (hf / hf-mirror / manual / ask)
            include_optional: Also download optional larger models
            endpoint: Custom Hugging Face mirror endpoint

        Returns:
            True if all required models downloaded successfully.
        """
        from subtap.schemas.config import load_config
        from subtap.core.models import ModelDownloader, MODEL_REGISTRY

        config = load_config(Path.home() / ".subtap" / "config.yaml")
        if endpoint:
            config.models.hf_mirror_endpoint = endpoint
        downloader = ModelDownloader(config)
        selected = self.choose_download_source(source)
        if selected == "manual":
            self.print_manual_model_instructions()
            return False

        # 检测网络连通性
        import typer
        first_model = "asr_0.6b"
        repo = MODEL_REGISTRY[first_model]["hf_repo"]
        typer.echo(f"▸ 检测 {selected} 连通性...")
        if not downloader.check_connectivity(selected, repo):
            typer.echo(f"  ✗ 无法连接到 {selected}")
            if selected == "ask":
                typer.echo("  请选择其他下载方式或手动安装")
                return False
            # 非交互模式，提示用户切换
            typer.echo(f"  提示：请使用 --download-source 参数选择其他下载方式")
            return False
        typer.echo(f"  ✓ {selected} 连通正常")

        targets = ["asr_0.6b", "aligner"]
        if include_optional:
            targets.append("asr_1.7b")
        results = [self._download_model(downloader, name, selected) for name in targets]
        return all(results)

    def print_manual_model_instructions(self) -> None:
        """Print instructions for manual model placement."""
        import typer
        typer.echo("请手动下载模型并放入项目根目录的 models/ 目录：")
        typer.echo("  - models/asr_0.6b/（必需）")
        typer.echo("  - models/aligner/（必需）")
        typer.echo("  - models/asr_1.7b/（可选，高质量 ASR）")
        typer.echo("")
        typer.echo("每个模型目录需要包含：config.json 和 model.safetensors")

    def _download_model(self, downloader, model_name: str, source: str = "hf") -> bool:
        """Download a single model with progress bar.

        Args:
            downloader: ModelDownloader instance
            model_name: Name of model to download
            source: Download source

        Returns:
            True if download succeeded.
        """
        import typer
        from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn

        typer.echo(f"▸ 下载 {model_name}...")
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
            ) as progress:
                task_id = progress.add_task(model_name, total=None)

                def update_progress(filename: str, downloaded: int, total: int) -> None:
                    if total > 0 and progress.tasks[task_id].total is None:
                        progress.update(task_id, total=total)
                    progress.update(task_id, completed=downloaded, description=f"{model_name}/{filename}")

                downloader.download(model_name, source=source, progress=update_progress)
            typer.echo(f"  ✓ {model_name} 下载完成")
            return True
        except NotImplementedError:
            logger.warning("模型 %s 下载未实现", model_name)
            typer.echo(f"  ✗ {model_name} 下载未实现")
            return False
        except Exception as e:
            logger.warning("模型 %s 下载失败: %s", model_name, e)
            typer.echo(f"  ✗ {model_name} 下载失败: {e}")
            return False
