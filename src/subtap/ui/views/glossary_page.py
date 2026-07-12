"""Glossary management page."""

from __future__ import annotations


class GlossaryPage:
    """Hotword list with add/delete/edit actions."""

    def build_glossary_items(self, hotwords: list) -> list[str]:
        """Build menu items from hotword list."""
        if not hotwords:
            return ["暂无热词，按 A 添加"]
        items = []
        for hw in hotwords:
            aliases = ", ".join(hw.aliases[:3])
            if len(hw.aliases) > 3:
                aliases += f" ...（共 {len(hw.aliases)} 个）"
            items.append(f"{hw.word} = {aliases}")
        return items

    def get_actions(self) -> list[str]:
        """Get available actions."""
        return ["添加 (A)", "删除 (D)", "编辑 (E)", "返回 (Esc)"]
