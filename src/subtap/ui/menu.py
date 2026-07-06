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
        offset: int = 0,
    ):
        self.title = title
        self.items = items
        self.footer = footer
        self.theme = theme or Theme()
        self.cursor = 0
        self.top_index = 0
        self.offset = offset  # 渲染起始行偏移（用于 logo 占位）
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
        lines.append(f"\033[2K{t.GRAY}{self.footer}{t.NC}")
        return lines

    def render_full(self) -> None:
        buf = ["\033[2J\033[H"]  # 清屏 + 光标归位
        for row, line in enumerate(self.render(), start=self.offset + 1):
            buf.append(f"\033[{row};1H\033[2K{line}")
        buf.append("\033[?25l")
        sys.stderr.write("".join(buf))
        sys.stderr.flush()
        self._needs_full_redraw = False

    def render_incremental(self, old_cursor: int) -> None:
        if self._needs_full_redraw:
            self.render_full()
            return
        t = self.theme
        # 旧行取消高亮（+2: title + blank line, +offset: logo 占位）
        old_row = old_cursor - self.top_index + 2 + self.offset
        sys.stderr.write(f"\r\033[{old_row};1H\033[2K  {self.items[old_cursor]}")
        # 新行高亮
        new_row = self.cursor - self.top_index + 2 + self.offset
        sys.stderr.write(f"\r\033[{new_row};1H\033[2K{t.CYAN}{ICON_ARROW} {self.items[self.cursor]}{t.NC}")
        # 光标移到页脚后（使用实际可见项数，不用 items_per_page）
        visible = min(self.items_per_page, len(self.items) - self.top_index)
        footer_row = visible + 3 + self.offset
        sys.stderr.write(f"\r\033[{footer_row};1H")
        sys.stderr.flush()

    def set_needs_redraw(self) -> None:
        self._needs_full_redraw = True
