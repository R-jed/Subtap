"""Multi-step subtitle creation wizard."""

from __future__ import annotations

import sys
from pathlib import Path


class WizardView:
    """6-step wizard: file -> quality -> glossary -> manuscript -> output -> confirm."""

    STEPS = [
        "选择音视频",
        "选择质量",
        "选择热词表",
        "选择参考文稿",
        "选择输出位置",
        "确认并开始",
    ]

    def __init__(self):
        self._state = {
            "step": 0,
            "file_path": None,
            "quality": None,  # "fast" or "quality"
            "glossary_name": None,
            "manuscript_name": None,
            "output_dir": None,
            "subtitle_lang": "zh",
            "subtitle_format": "srt",
        }

    def get_state(self) -> dict:
        return dict(self._state)

    def select_file(self, path: Path) -> None:
        self._state["file_path"] = path

    def select_quality(self, quality: str) -> None:
        self._state["quality"] = quality

    def select_glossary(self, name: str | None) -> None:
        self._state["glossary_name"] = name

    def select_manuscript(self, name: str | None) -> None:
        self._state["manuscript_name"] = name

    def select_output_dir(self, path: Path) -> None:
        self._state["output_dir"] = path

    def next_step(self) -> int:
        self._state["step"] = min(self._state["step"] + 1, len(self.STEPS) - 1)
        return self._state["step"]

    def prev_step(self) -> int:
        self._state["step"] = max(self._state["step"] - 1, 0)
        return self._state["step"]

    def is_complete(self) -> bool:
        return (
            self._state["file_path"] is not None
            and self._state["quality"] is not None
        )

    def build_run_command(self) -> list[str]:
        """Build the CLI command to execute."""
        if not self._state["file_path"]:
            return []
        cmd = [sys.executable, "-m", "subtap.cli", "run", str(self._state["file_path"])]
        fmt = self._state["subtitle_format"]
        if fmt:
            cmd.extend(["--format", fmt])
        lang = self._state["subtitle_lang"]
        if lang:
            cmd.extend(["--subtitle-language", lang])
        return cmd

    def get_confirm_items(self) -> list[str]:
        """Build confirmation screen items."""
        s = self._state
        fp = s["file_path"]
        display_name = Path(fp).name if fp else "未选择"
        items = [f"文件：{display_name}"]
        items.append(f"质量：{'快速' if s['quality'] == 'fast' else '高质量'}")
        if s["glossary_name"]:
            items.append(f"热词表：{s['glossary_name']}")
        if s["manuscript_name"]:
            items.append(f"参考文稿：{s['manuscript_name']}")
        items.append(f"输出：{s['output_dir'] or '默认目录'}")
        return items
