"""Version management for output system."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class VersionManager:
    """Manages output versions."""

    def __init__(self, output_dir: Path, input_name: str):
        """Initialize version manager.

        Args:
            output_dir: Base output directory
            input_name: Input file name stem
        """
        self.output_dir = output_dir
        self.input_name = input_name
        self._base_dir = output_dir / input_name

    def next_version(self) -> int:
        """Get next version number.

        Returns:
            Next version number
        """
        if not self._base_dir.exists():
            return 1

        existing = [
            int(p.name[1:])
            for p in self._base_dir.iterdir()
            if p.is_dir() and p.name.startswith("v") and p.name[1:].isdigit()
        ]

        if not existing:
            return 1

        return max(existing) + 1

    def get_version_dir(self, version: int) -> Path:
        """Get version directory path.

        Args:
            version: Version number

        Returns:
            Path to version directory
        """
        return self._base_dir / f"v{version}"

    def create_latest_link(self, version: int) -> None:
        """Create latest symlink.

        Args:
            version: Version to point to
        """
        # Ensure version directory exists
        version_dir = self.get_version_dir(version)
        version_dir.mkdir(parents=True, exist_ok=True)

        latest_link = self._base_dir / "latest"

        # Remove existing link
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()

        # Create new symlink
        latest_link.symlink_to(f"v{version}")
        logger.info("创建 latest 链接: %s -> v%d", latest_link, version)

    def cleanup_old_versions(self, keep_last: int = 5) -> None:
        """Clean up old versions.

        Args:
            keep_last: Number of recent versions to keep
        """
        if not self._base_dir.exists():
            return

        existing = sorted(
            [p for p in self._base_dir.iterdir() if p.is_dir() and p.name.startswith("v")],
            key=lambda p: int(p.name[1:])
        )

        if len(existing) <= keep_last:
            return

        for old_version in existing[:-keep_last]:
            shutil.rmtree(old_version)
            logger.info("清理旧版本: %s", old_version)
