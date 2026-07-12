"""Model management page."""

from __future__ import annotations


class ModelsPage:
    """Model list with install/delete/info actions."""

    def build_model_items(self, statuses: list) -> list[str]:
        """Build menu items from model statuses."""
        items = []
        for s in statuses:
            icon = "✓" if s.installed else "✗"
            detail = ""
            if not s.installed and s.missing_files:
                detail = f"（缺 {len(s.missing_files)} 个文件）"
            items.append(f"{icon} {s.name}{detail}")
        return items

    def get_actions(self, installed: bool) -> list[str]:
        """Get available actions for a model."""
        if installed:
            return ["查看详情", "删除", "返回"]
        return ["安装", "返回"]

    def format_model_detail(self, name: str, info: dict) -> list[str]:
        """Format model detail for display."""
        lines = [f"模型：{name}"]
        lines.append(f"描述：{info.get('description', '')}")
        lines.append(f"路径：{info.get('path', '')}")
        if info.get("hf_repo"):
            lines.append(f"HuggingFace：{info['hf_repo']}")
        return lines
