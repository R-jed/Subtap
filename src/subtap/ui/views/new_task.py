"""新建转录视图 — 文件选择和确认。"""
from pathlib import Path
from ..config_manager import ConfigManager


LANG_MAP = {"zh": "中文", "en": "英文", "ja": "日文"}


class NewTaskView:
    def __init__(self, config: ConfigManager, home_dir: Path):
        self.config = config
        self.home_dir = home_dir
        self.selected_file: Path | None = None

    def select_file(self, path: Path) -> None:
        self.selected_file = path

    def get_confirm_settings(self) -> dict:
        lang = self.config.get("output.subtitle_language")
        fmt = self.config.get("output.subtitle_formats", ["srt"])[0]
        return {
            "language": LANG_MAP.get(lang, "自动检测") if lang else "自动检测",
            "format": fmt.upper() if fmt else "SRT",
        }

    def build_run_command(self) -> list[str]:
        if not self.selected_file:
            return []
        cmd = ["subtap", "run", str(self.selected_file)]
        fmt = self.config.get("output.subtitle_formats", ["srt"])[0]
        if fmt:
            cmd.extend(["--format", fmt])
        return cmd
