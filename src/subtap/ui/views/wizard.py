"""Multi-step subtitle creation wizard."""

from __future__ import annotations

from pathlib import Path

from subtap.schemas.task_request import SubtitleTaskRequest


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
            "max_chars": None,
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

    def select_max_chars(self, max_chars: int) -> None:
        self._state["max_chars"] = max_chars

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
        """Return available glossary file paths from ~/.subtap/glossaries."""
        glossary_dir = Path.home() / ".subtap" / "glossaries"
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

    def build_request(self) -> SubtitleTaskRequest | None:
        """Build the shared task request from the selected values."""
        if not self._state["file_path"]:
            return None
        glossary_path = self._state["glossary_path"]
        manuscript_path = self._state["manuscript_path"]
        return SubtitleTaskRequest(
            input_path=self._state["file_path"],
            output_dir=self._state["output_dir"] or Path("./output"),
            mode=self._state["quality"],
            glossary_path=glossary_path,
            use_default_glossary=glossary_path is None,
            script_path=manuscript_path,
            disable_script=manuscript_path is None,
            reset_hotwords=True,
            subtitle_format=self._state["subtitle_format"],
            subtitle_language=self._state["subtitle_lang"],
            max_chars=self._state["max_chars"],
            local_only=True,
        )

    def build_run_command(self) -> list[str]:
        """Build the CLI command to execute."""
        request = self.build_request()
        return request.to_cli_command() if request is not None else []

    def get_confirm_items(self) -> list[str]:
        """Build confirmation screen items."""
        s = self._state
        fp = s["file_path"]
        display_name = Path(fp).name if fp else "未选择"
        items = [f"文件：{display_name}"]
        quality = {"fast": "快速", "quality": "高质量"}.get(
            s["quality"], "使用默认模型"
        )
        items.append(f"质量：{quality}")
        glossary = s["glossary_path"].name if s["glossary_path"] else "默认"
        items.append(f"热词表：{glossary}")
        manuscript = s["manuscript_path"].name if s["manuscript_path"] else "不使用"
        items.append(f"参考文稿：{manuscript}")
        items.append(f"字幕最大字数：{s['max_chars'] or '使用默认值'}")
        items.append(f"输出：{s['output_dir'] or '默认目录'}")
        return items
