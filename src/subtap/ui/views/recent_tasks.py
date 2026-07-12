"""Recent tasks page."""

from __future__ import annotations


class RecentTasksPage:
    """最近任务列表，支持查看详情。"""

    def build_items(self, tasks: list[dict]) -> list[str]:
        """Build menu items from StateStore.load().recent_tasks."""
        if not tasks:
            return ["暂无最近任务"]
        items = []
        for t in tasks:
            tid = t.get("task_id", "?")
            name = t.get("input_name", "?")
            time_str = t.get("time", "")
            date = time_str[:10] if time_str else ""
            items.append(f"{tid}  {name}  {date}")
        return items

    def get_actions(self) -> list[str]:
        """Get available actions."""
        return ["查看详情 (Enter)", "返回 (Esc)"]
