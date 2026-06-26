"""Naming strategy for output files."""

from __future__ import annotations

from pathlib import Path


class NamingStrategy:
    """Manages output file naming conventions."""

    def __init__(self, input_name: str, use_timestamp: bool = True):
        """Initialize naming strategy.

        Args:
            input_name: Input file name (e.g., 'video.mp3')
            use_timestamp: Whether to use timestamp in naming (reserved for future)
        """
        self.input_name = Path(input_name).stem
        self.use_timestamp = use_timestamp

    def get_final_name(self, ext: str) -> str:
        """Get final output file name.

        Args:
            ext: File extension (e.g., 'srt', 'ass')

        Returns:
            Final file name (e.g., 'video.srt')
        """
        return f"{self.input_name}.{ext}"

    def get_report_name(self) -> str:
        """Get report file name.

        Returns:
            Report file name (e.g., 'video_report.md')
        """
        return f"{self.input_name}_report.md"

    def get_metrics_name(self) -> str:
        """Get metrics file name.

        Returns:
            Metrics file name (e.g., 'video_metrics.json')
        """
        return f"{self.input_name}_metrics.json"

    def get_run_log_name(self) -> str:
        """Get run log file name.

        Returns:
            Run log file name (e.g., 'video_run.log.jsonl')
        """
        return f"{self.input_name}_run.log.jsonl"

    def get_artifact_name(self, name: str) -> str:
        """Get artifact file name.

        Args:
            name: Artifact name (e.g., 'asr', 'segments')

        Returns:
            Artifact file name (e.g., 'video_asr.json')
        """
        return f"{self.input_name}_{name}.json"
