"""Setup wizard business logic."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


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

    def setup_models(self, mode: str = "hybrid", quick: bool = False, full: bool = False) -> bool:
        """Setup models based on mode.

        Args:
            mode: Execution mode (fast/quality/hybrid)
            quick: Quick mode (only download 0.6B)
            full: Full mode (download all models)

        Returns:
            True if all required models downloaded successfully.
        """
        from subtap.schemas.config import load_config
        from subtap.core.models import ModelDownloader

        config = load_config(Path.home() / ".subtap" / "config.yaml")
        downloader = ModelDownloader(config)

        results = []

        # Always download aligner
        results.append(self._download_model(downloader, "aligner"))

        # ASR model selection
        if full:
            results.append(self._download_model(downloader, "asr_0.6b"))
            results.append(self._download_model(downloader, "asr_1.7b"))
        elif quick or mode == "fast":
            results.append(self._download_model(downloader, "asr_0.6b"))
        elif mode == "quality":
            results.append(self._download_model(downloader, "asr_1.7b"))
        else:
            # hybrid mode - default to 0.6B
            results.append(self._download_model(downloader, "asr_0.6b"))

        return all(results)

    def _download_model(self, downloader, model_name: str) -> bool:
        """Download a single model.

        Args:
            downloader: ModelDownloader instance
            model_name: Name of model to download

        Returns:
            True if download succeeded.
        """
        try:
            downloader.download(model_name)
            return True
        except NotImplementedError:
            # Model download not implemented yet
            return False
        except Exception:
            return False
