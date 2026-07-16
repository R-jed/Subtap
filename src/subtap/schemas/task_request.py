"""Shared request for starting a subtitle task."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from subtap.core.user_resources import default_glossary_path


@dataclass(frozen=True)
class SubtitleTaskRequest:
    """User choices shared by the TUI and the ``run`` command."""

    input_path: Path
    output_dir: Path
    mode: str
    glossary_path: Path | None = None
    use_default_glossary: bool = False
    script_path: Path | None = None
    disable_script: bool = False
    reset_hotwords: bool = False
    subtitle_format: str = "srt"
    subtitle_language: str | None = "zh"
    show_observer: bool = True

    def validate(self) -> None:
        """Reject choices that cannot describe one unambiguous task."""
        if not self.input_path.is_file():
            raise ValueError(f"输入文件不存在：{self.input_path}")
        if self.mode not in ("fast", "quality"):
            raise ValueError(f"--mode 必须是 fast/quality，收到：{self.mode}")
        if self.glossary_path is not None and self.use_default_glossary:
            raise ValueError("不能同时选择自定义热词表和默认热词表")
        glossary_path = self.resolved_glossary_path()
        if glossary_path is not None and not glossary_path.is_file():
            label = "默认热词表" if self.use_default_glossary else "热词表"
            raise ValueError(f"{label}不存在：{glossary_path}")
        if self.script_path is not None and self.disable_script:
            raise ValueError("不能同时选择参考文稿和不使用参考文稿")
        if self.script_path is not None and not self.script_path.is_file():
            raise ValueError(f"参考文稿不存在：{self.script_path}")
        if self.output_dir.exists() and not self.output_dir.is_dir():
            raise ValueError(f"输出位置不是目录：{self.output_dir}")

    def resolved_glossary_path(self) -> Path | None:
        """Return the exact glossary file selected for this task."""
        if self.glossary_path is not None:
            return self.glossary_path
        if self.use_default_glossary:
            return default_glossary_path()
        return None

    def to_cli_command(self) -> list[str]:
        """Return a command accepted by the public ``subtap run`` interface."""
        self.validate()
        command = [
            sys.executable,
            "-m",
            "subtap.cli",
            "run",
            str(self.input_path),
            "--mode",
            self.mode,
            "--format",
            self.subtitle_format,
        ]
        if self.subtitle_language is not None:
            command.extend(["--subtitle-language", self.subtitle_language])
        if self.glossary_path is not None:
            command.extend(["--glossary", str(self.glossary_path)])
        elif self.use_default_glossary:
            command.append("--default-glossary")
        if self.reset_hotwords:
            command.append("--reset-hotwords")
        if self.script_path is not None:
            command.extend(["--script", str(self.script_path)])
        elif self.disable_script:
            command.append("--no-script")
        command.extend(["--output-dir", str(self.output_dir)])
        if self.show_observer:
            command.append("--tui")
        return command
