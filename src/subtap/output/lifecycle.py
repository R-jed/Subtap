"""Output lifecycle management."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from subtap.output.exceptions import OutputError

logger = logging.getLogger(__name__)


class OutputLifecycle:
    """Manages output file writing lifecycle."""

    def __init__(self, version_dir: Path):
        """Initialize output lifecycle.

        Args:
            version_dir: Version directory path (e.g., output/video/v1)
        """
        self.version_dir = version_dir
        self.version_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir = self.version_dir / "artifacts"
        self._artifacts_dir.mkdir(exist_ok=True)
        self._written_files: list[Path] = []

    def init_output_task(self) -> None:
        """Initialize output task."""
        logger.info("初始化输出目录: %s", self.version_dir)

    def write_user_artifact(self, name: str, content: str) -> Path:
        """Write user-visible artifact.

        Args:
            name: File name (e.g., 'video.srt')
            content: File content

        Returns:
            Path to written file

        Raises:
            OutputError: If write fails
        """
        try:
            output_path = self.version_dir / name
            output_path.write_text(content, encoding="utf-8")
            self._written_files.append(output_path)
            logger.info("写入文件: %s", output_path)
            return output_path
        except OSError as e:
            logger.error("写入文件失败: %s - %s", name, e)
            raise OutputError(f"写入 {name} 失败: {e}") from e

    def write_report(self, content: str) -> Path:
        """Write report file.

        Args:
            content: Report content (markdown)

        Returns:
            Path to written report
        """
        return self.write_user_artifact("report.md", content)

    def write_metrics(self, metrics: dict) -> Path:
        """Write metrics file.

        Args:
            metrics: Metrics dictionary

        Returns:
            Path to written metrics
        """
        content = json.dumps(metrics, indent=2, ensure_ascii=False)
        return self.write_user_artifact("metrics.json", content)

    def write_artifacts(self, artifacts: dict[str, dict]) -> None:
        """Write intermediate artifacts.

        Args:
            artifacts: Dictionary of artifact name to content
        """
        for name, content in artifacts.items():
            try:
                output_path = self._artifacts_dir / f"{name}.json"
                output_path.write_text(
                    json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                self._written_files.append(output_path)
                logger.info("写入 artifact: %s", output_path)
            except OSError as e:
                logger.error("写入 artifact 失败: %s - %s", name, e)
                raise OutputError(f"写入 artifact {name} 失败: {e}") from e

    def write_run_log(self, log_entry: dict) -> Path:
        """Append to run log.

        Args:
            log_entry: Log entry dictionary

        Returns:
            Path to run log
        """
        log_path = self.version_dir / "run.log.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        if log_path not in self._written_files:
            self._written_files.append(log_path)
        return log_path

    def finalize_output(self) -> dict:
        """Finalize output, generate checksum.

        Returns:
            Dictionary with files list and checksum
        """
        # Calculate checksum of all written files
        checksums = []
        for file_path in sorted(self._written_files):
            if file_path.exists():
                content = file_path.read_bytes()
                file_hash = hashlib.sha256(content).hexdigest()[:16]
                checksums.append(f"{file_path.name}:{file_hash}")

        combined_checksum = hashlib.sha256("|".join(checksums).encode()).hexdigest()[
            :16
        ]

        result = {
            "files": [
                str(f.relative_to(self.version_dir)) for f in self._written_files
            ],
            "checksum": combined_checksum,
            "version_dir": str(self.version_dir),
        }

        logger.info("输出完成: %s", self.version_dir)
        return result
