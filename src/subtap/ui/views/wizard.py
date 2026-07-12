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
            "glossary_path": None,
            "manuscript_path": None,
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

    def select_glossary(self, path: Path | None) -> None:
        self._state["glossary_path"] = path

    def select_manuscript(self, path: Path | None) -> None:
        self._state["manuscript_path"] = path

    def select_output_dir(self, path: Path | None) -> None:
        self._state["output_dir"] = path

    def next_step(self) -> int:
        self._state["step"] = min(self._state["step"] + 1, len(self.STEPS) - 1)
        return self._state["step"]

    def prev_step(self) -> int:
        self._state["step"] = max(self._state["step"] - 1, 0)
        return self._state["step"]

    def is_complete(self) -> bool:
        return (
            self._state["file_path"] is not None and self._state["quality"] is not None
        )

    @staticmethod
    def list_glossaries() -> list[Path]:
        """Return available glossary file paths from ~/.subtap/glossary."""
        glossary_dir = Path.home() / ".subtap" / "glossary"
        if not glossary_dir.is_dir():
            return []
        return sorted(
            f
            for f in glossary_dir.iterdir()
            if f.is_file() and f.suffix in (".txt", ".yaml", ".yml", ".json")
        )

    @staticmethod
    def list_manuscripts() -> list[Path]:
        """Return available manuscript file paths from ~/.subtap/manuscripts."""
        ms_dir = Path.home() / ".subtap" / "manuscripts"
        if not ms_dir.is_dir():
            return []
        return sorted(
            f
            for f in ms_dir.iterdir()
            if f.is_file() and f.suffix in (".txt", ".md", ".docx")
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
        # glossary -> stored full path
        glossary_path = self._state["glossary_path"]
        if glossary_path:
            cmd.extend(["--glossary", str(glossary_path)])
        # manuscript -> stored full path
        manuscript_path = self._state["manuscript_path"]
        if manuscript_path:
            cmd.extend(["--script", str(manuscript_path)])
        # output directory
        output_dir = self._state["output_dir"]
        if output_dir:
            cmd.extend(["--output-dir", str(output_dir)])
        return cmd

    def get_confirm_items(self) -> list[str]:
        """Build confirmation screen items."""
        s = self._state
        fp = s["file_path"]
        display_name = Path(fp).name if fp else "未选择"
        items = [f"文件：{display_name}"]
        items.append(f"质量：{'快速' if s['quality'] == 'fast' else '高质量'}")
        if s["glossary_path"]:
            items.append(f"热词表：{s['glossary_path'].name}")
        if s["manuscript_path"]:
            items.append(f"参考文稿：{s['manuscript_path'].name}")
        items.append(f"输出：{s['output_dir'] or '默认目录'}")
        return items
