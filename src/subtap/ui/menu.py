"""ANSI 菜单框架。

移植自 Mole 的 menu_paginated.sh。
- 增量渲染（只更新变化的行）
- 分页滚动
- 状态栏
"""
import os
import sys
from .theme import Theme, ICON_ARROW, get_display_width


class Menu:
    """交互式分页菜单。"""

    def __init__(
        self,
        title: str,
        items: list[str],
        footer: str = "↑↓ 导航  Enter 确认  Q 退出",
        theme: Theme | None = None,
        max_items: int = 50,
        prefix_lines: list[str] | None = None,
    ):
        self.title = title
        self.items = items
        self.footer = footer
        self.theme = theme or Theme()
        self.cursor = 0
        self.top_index = 0
        self.prefix_lines = prefix_lines or []  # 菜单前的内容（如 logo）
        self.offset = len(self.prefix_lines)
        self.items_per_page = self._calc_items_per_page(max_items)
        self._needs_full_redraw = True

    def _calc_items_per_page(self, max_items: int) -> int:
        try:
            lines = os.get_terminal_size().lines
        except OSError:
            lines = 24
        reserved = 4  # title + blank + footer + buffer
        available = lines - reserved
        return max(1, min(available, max_items))

    def move_up(self) -> None:
        if self.cursor > 0:
            self.cursor -= 1
            if self.cursor < self.top_index:
                self.top_index = self.cursor
                self._needs_full_redraw = True

    def move_down(self) -> None:
        if self.cursor < len(self.items) - 1:
            self.cursor += 1
            if self.cursor >= self.top_index + self.items_per_page:
                self.top_index = self.cursor - self.items_per_page + 1
                self._needs_full_redraw = True

    def jump_top(self) -> None:
        self.cursor = 0
        self.top_index = 0
        self._needs_full_redraw = True

    def jump_bottom(self) -> None:
        self.cursor = len(self.items) - 1
        self.top_index = max(0, self.cursor - self.items_per_page + 1)
        self._needs_full_redraw = True

    def selected_item(self) -> str:
        if not self.items:
            return ""
        return self.items[self.cursor]

    def render(self) -> list[str]:
        t = self.theme
        lines = []
        lines.append(f"\033[2K{t.PURPLE_BOLD}{self.title}{t.NC}")
        lines.append("\033[2K")
        # 只渲染实际可见的菜单项（不超过 items_per_page）
        visible = min(self.items_per_page, len(self.items) - self.top_index)
        for i in range(visible):
            idx = self.top_index + i
            is_current = idx == self.cursor
            if is_current:
                lines.append(f"\033[2K{t.CYAN}{ICON_ARROW} {self.items[idx]}{t.NC}")
            else:
                lines.append(f"\033[2K  {self.items[idx]}")
        # 菜单和状态栏之间间距（5行）
        lines.append("\033[2K")
        lines.append("\033[2K")
        lines.append("\033[2K")
        lines.append("\033[2K")
        lines.append("\033[2K")
        lines.append(f"\033[2K{t.GRAY}{self.footer}{t.NC}")
        return lines

    def render_full(self) -> None:
        buf = ["\033[2J\033[H"]  # 清屏 + 光标归位
        # 先写 prefix（如 logo），再写菜单
        for row, line in enumerate(self.prefix_lines, start=1):
            buf.append(f"\033[{row};1H{line}")
        for row, line in enumerate(self.render(), start=self.offset + 1):
            buf.append(f"\033[{row};1H\033[2K{line}")
        buf.append("\033[?25l")
        sys.stderr.write("".join(buf))
        sys.stderr.flush()
        self._needs_full_redraw = False

    def render_incremental(self, old_cursor: int) -> None:
        # 增量渲染 = 重绘菜单区域（从第一项开始，不清屏，保留 logo）
        # 用 \033[row;1H 逐行覆盖，避免依赖 \033[H 的终端兼容性
        t = self.theme
        buf = []
        # 重写菜单项（从 offset+3 开始，跳过 title 和 blank）
        start_row = self.offset + 3
        visible = min(self.items_per_page, len(self.items) - self.top_index)
        for i in range(visible):
            idx = self.top_index + i
            row = start_row + i
            is_current = idx == self.cursor
            if is_current:
                buf.append(f"\033[{row};1H\033[2K{t.CYAN}{ICON_ARROW} {self.items[idx]}{t.NC}")
            else:
                buf.append(f"\033[{row};1H\033[2K  {self.items[idx]}")
        sys.stderr.write("".join(buf))
        sys.stderr.flush()

    def set_needs_redraw(self) -> None:
        self._needs_full_redraw = True
