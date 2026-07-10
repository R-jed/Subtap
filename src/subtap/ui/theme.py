"""颜色语义映射、NO_COLOR 支持、CJK 宽度计算。

移植自 Mole 的 lib/core/base.sh 和 lib/core/ui.sh。
"""

import os
import unicodedata


class Theme:
    """8 色语义映射，遵守 no-color.org 规范。"""

    def __init__(self):
        if self._should_disable_color():
            self.GREEN = ""
            self.BLUE = ""
            self.CYAN = ""
            self.YELLOW = ""
            self.PURPLE = ""
            self.PURPLE_BOLD = ""
            self.RED = ""
            self.GRAY = ""
            self.NC = ""
        else:
            self.GREEN = "\033[0;32m"
            self.BLUE = "\033[1;34m"
            self.CYAN = "\033[0;36m"
            self.YELLOW = "\033[0;33m"
            self.PURPLE = "\033[0;35m"
            self.PURPLE_BOLD = "\033[1;35m"
            self.RED = "\033[0;31m"
            self.GRAY = "\033[0;90m"
            self.NC = "\033[0m"

    @staticmethod
    def _should_disable_color() -> bool:
        return "NO_COLOR" in os.environ

    def colorize_size(self, size_str: str) -> str:
        if size_str.endswith("GB"):
            return f"{self.RED}{size_str}{self.NC}"
        elif size_str.endswith("MB"):
            return f"{self.YELLOW}{size_str}{self.NC}"
        elif size_str.endswith("KB"):
            return f"{self.GREEN}{size_str}{self.NC}"
        elif size_str.endswith("B"):
            return f"{self.GRAY}{size_str}{self.NC}"
        return size_str


ICON_ARROW = "➤"
ICON_EMPTY = "○"
ICON_SOLID = "●"
ICON_CHECK = "✓"
ICON_CROSS = "✗"
ICON_DOT = "·"
ICON_SPINNER = "⠙"  # 进行中，spinner.py 使用


def get_display_width(text: str) -> int:
    width = 0
    for ch in text:
        if ch in ("‍", "️"):
            continue
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1
    return width


def truncate_by_width(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    ellipsis_width = get_display_width("...")
    width = 0
    for i, ch in enumerate(text):
        if ch in ("‍", "️"):
            continue
        eaw = unicodedata.east_asian_width(ch)
        cw = 2 if eaw in ("W", "F") else 1
        if width + cw + ellipsis_width > max_width:
            return text[:i] + "..."
        width += cw
    return text
