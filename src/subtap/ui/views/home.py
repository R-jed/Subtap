"""New home page with status awareness."""

from __future__ import annotations

from pathlib import Path

from .status_bar import StatusBar


class HomeView:
    """Home page with status bar and menu."""

    MENU_ITEMS = [
        "1. 新建字幕    从音频/视频生成字幕",
        "2. 最近任务    查看历史、重新生成",
        "3. 模型管理    下载、查看、删除模型",
        "4. 热词库      管理专有名词和热词",
        "5. 文稿库      管理参考文稿",
        "6. 设置        模型、接口、偏好",
        "7. 系统检查    查看诊断信息",
    ]

    def __init__(self, subtap_root: Path | None = None):
        self.root = subtap_root or (Path.home() / ".subtap")
        self.status_bar = StatusBar(self.root)

    def is_first_run(self) -> bool:
        """Check if this is the first run (no state.json)."""
        return not (self.root / "state.json").exists()

    def build_menu_items(self) -> list[str]:
        return list(self.MENU_ITEMS)

    def build_prefix_lines(self) -> list[str]:
        """Build logo + status bar prefix lines."""
        from subtap.ui.theme import Theme

        t = Theme()
        prefix = [
            f"{t.CYAN} ___      _    _             {t.NC}",
            f"{t.CYAN}/ __|_  _| |__| |_ __ _ _ __ {t.NC}",
            f"{t.CYAN}\\__ \\ || | '_ \\  _/ _` | '_ \\{t.NC}",
            f"{t.CYAN}|___/\\_,_|_.__/\\__\\__,_| .__/{t.NC}",
            f"{t.CYAN}                       |_|   {t.NC}",
            f"{t.GRAY}          字幕生成工具{t.NC}",
            "",
        ]
        # Status bar (3 lines)
        prefix.extend(self.status_bar.render())
        prefix.append("")
        return prefix

    def map_selection_to_state(self, index: int) -> str | None:
        """Map menu index to target state name."""
        mapping = {
            0: "wizard",
            1: "recent_tasks",
            2: "models_page",
            3: "glossary_page",
            4: "manuscripts_page",
            5: "settings",
            6: "doctor",
        }
        return mapping.get(index)
