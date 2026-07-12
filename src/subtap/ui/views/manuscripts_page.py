"""Manuscripts management page."""

from __future__ import annotations


class ManuscriptsPage:
    """文稿列表，支持添加/删除/查看最近使用。"""

    def build_items(self, manuscripts: list[dict]) -> list[str]:
        """Build menu items from ManuscriptIndex.list_all() output."""
        if not manuscripts:
            return ["暂无文稿，按 A 添加"]
        items = []
        for m in manuscripts:
            icon = "✓" if m["exists"] else "✗"
            recent = ""
            if m.get("recent_use_time"):
                recent = f"  {m['recent_use_time'][:10]}"
            items.append(f"{icon} {m['name']}{recent}")
        return items

    def get_actions(self) -> list[str]:
        """Get available actions."""
        return ["添加 (A)", "删除 (D)", "返回 (Esc)"]
