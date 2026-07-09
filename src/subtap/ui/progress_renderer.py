"""ANSI pipeline progress renderer.

Tails run.log.jsonl, parses EventBus events, renders pipeline stage progress
with ANSI escape codes in real-time.
"""

import json
import threading
import time
from pathlib import Path
from typing import IO, Any

# ANSI color codes
CYAN = "\033[36m"
PURPLE_BOLD = "\033[35;1m"
GREEN = "\033[32m"
GRAY = "\033[90m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

# Spinner frames
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Model display name mapping
MODEL_DISPLAY_MAP = {
    "asr_0.6b": "快速",
    "asr_1.7b": "高质量",
    "asr-fast": "快速",
    "asr-quality": "高质量",
    "aligner_0.6b": "对齐",
}

# Pipeline stage order
STAGE_ORDER = [
    ("prepare", "音频标准化"),
    ("chunk", "音频切段"),
    ("asr", "语音识别"),
    ("clean", "文本清洗"),
    ("segment", "智能断句"),
    ("align", "时间轴对齐"),
    ("hotword", "热词替换"),
    ("learn", "热词学习"),
    ("translate", "字幕翻译"),
    ("export", "字幕导出"),
]


def _model_display_name(model_name: str) -> str:
    """Get display name for model."""
    return MODEL_DISPLAY_MAP.get(model_name, model_name)


class PipelineProgressRenderer:
    """ANSI-based pipeline progress renderer.

    Reads JSONL event log and renders real-time progress with ANSI escapes.
    """

    def __init__(self, stderr: IO[str] | None = None) -> None:
        """Initialize renderer.

        Args:
            stderr: Output stream (defaults to stderr)
        """
        self._stderr = stderr
        self._lock = threading.Lock()

        # Stage tracking
        self._current_stage: str | None = None
        self._current_stage_cn: str = ""
        self._stage_index: int = 0
        self._completed_stages: int = 0
        self._total_stages: int = len(STAGE_ORDER)

        # Progress tracking
        self._stage_progress: float = 0.0
        self._model_name: str | None = None
        self._spinner_index: int = 0
        self._rendered_lines: int = 0

        # Timing
        self._start_time: float = 0.0
        self._total_time: float = 0.0

        # File reading state
        self._file_offset: int = 0

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Process a single EventBus event.

        Args:
            event: Event dictionary with event_type and data
        """
        event_type = event.get("event_type", "")
        data = event.get("data", {})

        if event_type == "stage_start":
            stage_name = data.get("stage", "")
            message_zh = data.get("message_zh", stage_name)

            # Find stage index
            for i, (name, _) in enumerate(STAGE_ORDER):
                if name == stage_name:
                    self._stage_index = i + 1
                    break

            self._current_stage = stage_name
            self._current_stage_cn = message_zh
            self._stage_progress = 0.0

        elif event_type == "stage_end":
            self._completed_stages += 1

        elif event_type in (
            "asr_draft_ready", "audio_chunk_ready", "enhancement_ready",
            "sentence_candidate_ready", "alignment_ready", "progress",
        ):
            progress = data.get("progress", 0)
            self._stage_progress = float(progress)

        elif event_type == "model_load_start":
            self._model_name = data.get("model")

    def _read_new_events(self, log_path: Path) -> list[dict[str, Any]]:
        """Read new events from JSONL file (incremental).

        Args:
            log_path: Path to JSONL event log

        Returns:
            List of new events
        """
        events = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # seek to end
                file_size = f.tell()
                if self._file_offset > file_size:
                    self._file_offset = 0  # 文件被截断，重置
                f.seek(self._file_offset)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                self._file_offset = f.tell()
        except FileNotFoundError:
            pass
        return events

    def _build_bar(self, progress: float, width: int = 20) -> str:
        """Build progress bar string.

        Args:
            progress: Progress percentage (0-100)
            width: Bar width in characters

        Returns:
            ANSI-colored progress bar
        """
        progress = max(0.0, min(100.0, progress))
        filled = int(width * progress / 100)
        empty = width - filled
        return f"{GREEN}{'█' * filled}{GRAY}{'░' * empty}{RESET}"

    def _build_lines(self) -> list[str]:
        """Build rendered output lines.

        Returns:
            List of ANSI-colored output lines
        """
        lines = []

        # Spinner
        spinner = SPINNER_FRAMES[self._spinner_index % len(SPINNER_FRAMES)]

        # Stage info
        stage_num = f"[{self._stage_index}/{self._total_stages}]"
        stage_name = self._current_stage_cn or "准备中"

        # Progress bar and percentage
        bar = self._build_bar(self._stage_progress)
        percent = f"{YELLOW}{int(self._stage_progress)}%{RESET}"

        # Elapsed time
        elapsed = time.time() - self._start_time if self._start_time else 0
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        time_str = f"{GRAY}{minutes}:{seconds:02d}{RESET}"

        # Main progress line
        line1 = f"  {CYAN}{spinner}{RESET} {PURPLE_BOLD}{stage_num} {stage_name}{RESET}  {bar}  {percent}  {time_str}"
        lines.append(line1)

        # Model line (if applicable)
        if self._model_name:
            model_display = _model_display_name(self._model_name)
            lines.append(f"    {GRAY}模型：{CYAN}{model_display}{RESET}")

        return lines

    def _render(self, lines: list[str]) -> None:
        """Render lines with in-place overwrite.

        Args:
            lines: Lines to render
        """
        if not self._stderr:
            return

        # Move up by PREVIOUS rendered line count (not current)
        for _ in range(self._rendered_lines):
            self._stderr.write("\033[A\033[2K")

        # Write new lines
        for line in lines:
            self._stderr.write(line + "\r\n")

        self._stderr.flush()
        self._rendered_lines = len(lines)

    def _build_result_lines(self, success: bool, output_path: str | None = None) -> list[str]:
        """Build final result lines.

        Args:
            success: Whether pipeline succeeded
            output_path: Output file path

        Returns:
            List of result lines
        """
        lines = []

        if success:
            # Calculate total time
            elapsed = self._total_time or (time.time() - self._start_time if self._start_time else 0)
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)

            lines.append(f"  {GREEN}✓ 转录完成{RESET}  {GRAY}{minutes}:{seconds:02d}{RESET}")
            if output_path:
                lines.append(f"  {GRAY}输出：{RESET}{output_path}")
        else:
            lines.append(f"  {RED}✗ 转录失败{RESET}")

        return lines

    def run(
        self,
        log_path: Path,
        process: Any,
        output_path: str | None = None,
    ) -> bool:
        """Main render loop.

        Args:
            log_path: Path to JSONL event log
            process: Subprocess to monitor
            output_path: Output file path

        Returns:
            True if successful
        """
        self._start_time = time.time()

        # Initial render
        with self._lock:
            lines = self._build_lines()
            self._render(lines)

        # Poll loop
        while process.poll() is None:
            with self._lock:
                # Read new events
                events = self._read_new_events(log_path)
                for event in events:
                    self._handle_event(event)

                # Update spinner
                self._spinner_index += 1

                # Render
                lines = self._build_lines()
                self._render(lines)

            time.sleep(0.25)  # 250ms throttle

        # Process finished
        self._total_time = time.time() - self._start_time
        success = process.returncode == 0

        # Final render
        with self._lock:
            result_lines = self._build_result_lines(success, output_path)
            self._render(result_lines)

        return success
