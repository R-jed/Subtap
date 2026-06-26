"""Setup wizard business logic."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


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
        except Exception:
            return False
