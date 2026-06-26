"""Output engine core."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from subtap.output.exceptions import OutputError
from subtap.output.lifecycle import OutputLifecycle
from subtap.output.naming import NamingStrategy
from subtap.output.versioning import VersionManager
from subtap.schemas.config import OutputConfig

logger = logging.getLogger(__name__)


class OutputEngine:
    """Unified output management engine."""

    def __init__(self, output_dir: Path, input_name: str, config: OutputConfig):
        """Initialize output engine.

        Args:
            output_dir: Base output directory
            input_name: Input file name (e.g., 'video.mp3')
            config: Output configuration
        """
        self.output_dir = output_dir
        self.input_name = Path(input_name).stem
        self.config = config

        # Initialize components
        self.naming = NamingStrategy(input_name)
        self.version_manager = VersionManager(output_dir, self.input_name)
        self.version = self.version_manager.next_version()

        # Get version directory and initialize lifecycle
        version_dir = self.version_manager.get_version_dir(self.version)
        self.lifecycle = OutputLifecycle(version_dir)

        logger.info("初始化 OutputEngine: %s v%d", self.input_name, self.version)

    def write_final(self, ext: str, content: str) -> Path:
        """Write final output file.

        Args:
            ext: File extension (e.g., 'srt', 'ass')
            content: File content

        Returns:
            Path to written file
        """
        name = self.naming.get_final_name(ext)
        return self.lifecycle.write_user_artifact(name, content)

    def write_report(self, content: str) -> Path:
        """Write report file.

        Args:
            content: Report content (markdown)

        Returns:
            Path to written report
        """
        name = self.naming.get_report_name()
        return self.lifecycle.write_user_artifact(name, content)

    def write_metrics(self, metrics: dict) -> Path:
        """Write metrics file.

        Args:
            metrics: Metrics dictionary

        Returns:
            Path to written metrics
        """
        name = self.naming.get_metrics_name()
        return self.lifecycle.write_user_artifact(
            name,
            json.dumps(metrics, indent=2, ensure_ascii=False)
        )

    def write_run_log(self, log_entry: dict) -> Path:
        """Append to run log.

        Args:
            log_entry: Log entry dictionary

        Returns:
            Path to run log
        """
        return self.lifecycle.write_run_log(log_entry)

    def write_artifacts(self, artifacts: dict[str, dict]) -> None:
        """Write intermediate artifacts.

        Args:
            artifacts: Dictionary of artifact name to content
        """
        self.lifecycle.write_artifacts(artifacts)

    def finalize_output(self) -> dict:
        """Finalize output, create latest link, cleanup old versions.

        Returns:
            Dictionary with output summary
        """
        # Finalize lifecycle
        result = self.lifecycle.finalize_output()

        # Create latest symlink
        self.version_manager.create_latest_link(self.version)

        # Cleanup old versions
        if self.config.keep_versions > 0:
            self.version_manager.cleanup_old_versions(self.config.keep_versions)

        result["version"] = self.version
        result["input_name"] = self.input_name

        logger.info("输出完成: %s v%d", self.input_name, self.version)
        return result
