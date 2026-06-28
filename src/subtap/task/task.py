"""Task abstraction for one-command subtitle generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskResult:
    """Result of a completed subtitle generation task."""

    final_path: Path
    report_path: Path
    debug_path: Path
    quality_score: float = 0.0
    timings: dict[str, float] = field(default_factory=dict)


@dataclass
class Task:
    """One-command subtitle generation task.

    Encapsulates a complete subtitle generation workflow:
    - Input file
    - Execution mode (fast/quality)
    - Output format (srt/vtt/json)
    - Language and glossary settings

    Usage:
        task = Task(input_file=Path("video.mp3"), mode="quality")
        result = task.run(output_dir=Path("./output"))
    """

    input_file: Path
    mode: str = "fast"  # fast / quality
    output_format: str = "srt"  # srt / vtt / json
    language: str = "zh"  # zh / en
    glossary_profile: str = ""  # 术语表路径

    @property
    def asr_model_size(self) -> str:
        """ASR model size based on mode."""
        if self.mode == "quality":
            return "asr_1.7b"
        return "asr_0.6b"

    def create_output_structure(self, output_dir: Path) -> TaskResult:
        """Create output directory structure and return paths.

        Args:
            output_dir: Base output directory.

        Returns:
            TaskResult with paths for final, report, and debug files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        final_ext = {
            "srt": ".srt",
            "vtt": ".vtt",
            "json": ".json",
        }.get(self.output_format, ".srt")

        return TaskResult(
            final_path=output_dir / f"final{final_ext}",
            report_path=output_dir / "report.md",
            debug_path=output_dir / "debug.json",
        )

    def to_policy_mode(self) -> str:
        """Convert task mode to pipeline mode string.

        Returns:
            Mode string for pipeline decision.
        """
        return self.mode if self.mode in ("fast", "quality") else "fast"
