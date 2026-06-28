"""Setup wizard business logic."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import httpx
import yaml

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
        typer.echo("  3. ModelScope（https://modelscope.cn）")
        typer.echo("  4. 手动放入 models/")
        choice = typer.prompt("输入序号", default="1")
        mapping = {"1": "hf", "2": "hf-mirror", "3": "modelscope", "4": "manual"}
        if choice not in mapping:
            typer.echo(f"  无效选项 '{choice}'，默认使用 Hugging Face 直连")
        return mapping.get(choice, "hf")

    def setup_models(
        self,
        source: str = "ask",
        include_optional: bool = False,
        endpoint: str | None = None,
    ) -> bool:
        """Setup models with download source selection.

        Args:
            source: Download source (hf / hf-mirror / modelscope / manual / ask)
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
        self.last_model_source = selected
        if selected == "manual":
            self.print_manual_model_instructions()
            return False

        # 检测网络连通性
        import typer

        first_model = "asr_0.6b"

        def repo_for(download_source: str) -> str:
            if download_source == "modelscope":
                return MODEL_REGISTRY[first_model]["modelscope_repo"]
            return MODEL_REGISTRY[first_model]["hf_repo"]

        typer.echo(f"▸ 检测 {selected} 连通性...")
        if not downloader.check_connectivity(selected, repo_for(selected)):
            typer.echo(f"  ✗ 无法连接到 {selected}")

            if source != "ask":
                # 非交互模式：直接返回失败
                typer.echo("  提示：请使用 --download-source 参数选择其他下载方式")
                return False

            # 降级顺序：hf -> hf-mirror -> modelscope -> manual
            fallback_order = {
                "hf": "hf-mirror",
                "hf-mirror": "modelscope",
                "modelscope": "manual",
            }

            while selected in fallback_order:
                fallback = fallback_order[selected]
                typer.echo(f"  建议降级到: {fallback}")
                choice = typer.prompt("是否降级？(y/n)", default="y")
                if choice.lower() != "y":
                    return False

                if fallback == "manual":
                    self.last_model_source = "manual"
                    self.print_manual_model_instructions()
                    return False

                selected = fallback
                self.last_model_source = selected
                typer.echo(f"▸ 检测 {selected} 连通性...")
                if downloader.check_connectivity(selected, repo_for(selected)):
                    typer.echo(f"  ✓ {selected} 连通正常")
                    break

                typer.echo(f"  ✗ 无法连接到 {selected}")
            else:
                # 所有降级源均不可达
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
        from rich.progress import (
            Progress,
            SpinnerColumn,
            BarColumn,
            TextColumn,
            DownloadColumn,
            TransferSpeedColumn,
        )

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
                    # 每个文件开始时重置 task
                    if downloaded == 0:
                        progress.reset(
                            task_id, total=total, description=f"{model_name}/{filename}"
                        )
                    progress.update(task_id, completed=downloaded)

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

    def fetch_remote_models(
        self, base_url: str, api_key: str, timeout_sec: int = 60
    ) -> list[str]:
        """Fetch available models from an OpenAI-compatible /models endpoint."""
        url = f"{base_url.rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        with httpx.Client(timeout=timeout_sec) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
        payload = response.json()
        candidates = payload.get("data", payload.get("models", []))
        models: list[str] = []
        for item in candidates:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
        return models

    def configure_remote_api(
        self,
        provider: str = "openai-compatible",
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str = "SUBTAP_API_KEY",
        timeout_sec: int = 60,
    ) -> bool:
        """Configure remote API endpoint and selected model without saving the key."""
        import typer

        selected_base_url = base_url or typer.prompt("远程 API Base URL")
        selected_api_key = api_key or typer.prompt(
            "API Key（不会写入配置）", hide_input=True
        )

        typer.echo("▸ 获取远程模型列表...")
        try:
            models = self.fetch_remote_models(
                selected_base_url, selected_api_key, timeout_sec=timeout_sec
            )
        except Exception as e:
            logger.warning("远程模型列表获取失败: %s", e)
            typer.echo(f"  ✗ 获取模型列表失败：{e}")
            return False

        if not models:
            typer.echo("  ✗ 远程 API 未返回可用模型")
            return False

        typer.echo("请选择远程模型：")
        for index, model in enumerate(models, start=1):
            typer.echo(f"  {index}. {model}")

        choice = typer.prompt("输入序号", default="1")
        try:
            selected_model = models[int(choice) - 1]
        except (ValueError, IndexError):
            typer.echo(f"  无效选项 '{choice}'，默认使用第一个模型")
            selected_model = models[0]

        config_path = Path.home() / ".subtap" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        else:
            data = {}

        data["remote_api"] = {
            "provider": provider,
            "base_url": selected_base_url,
            "api_key_env": api_key_env,
            "model": selected_model,
            "timeout_sec": timeout_sec,
        }
        config_path.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        typer.echo(f"  ✓ 已保存远程 API 配置，模型：{selected_model}")
        typer.echo(f"  请在运行前设置环境变量：export {api_key_env}='你的 API Key'")
        return True
