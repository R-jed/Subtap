"""Task completion page."""

from __future__ import annotations

from pathlib import Path


class CompletionPage:
    """Shows task results with actions."""

    def build_items(self, output_path: str, duration_sec: float) -> list[str]:
        """Build menu items for completion page."""
        return [
            f"✓ 字幕已生成",
            f"  耗时：{self.format_duration(duration_sec)}",
            f"  输出：{output_path}",
            "",
            "1. 打开字幕",
            "2. 打开输出目录",
            "3. 重新生成",
            "4. 处理另一个文件",
        ]

    def format_duration(self, seconds: float) -> str:
        """Format seconds into human-readable duration."""
        if seconds < 60:
            return f"{int(seconds)} 秒"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes} 分 {secs} 秒"

    def get_actions(self) -> list[str]:
        return ["打开字幕", "打开输出目录", "重新生成", "处理另一个文件", "返回"]
