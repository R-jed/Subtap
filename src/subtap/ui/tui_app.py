"""TUI 主入口，页面路由状态机。

用 ANSI 原生渲染实现交互式终端 UI。
"""
import os
import sys
import subprocess
from pathlib import Path
from .keyboard import Key, KeyReader
from .theme import Theme
from .menu import Menu
from .spinner import Spinner
from .config_manager import ConfigManager
from .file_picker import FilePicker
from .views.new_task import NewTaskView
from .history import HistoryScanner


class TuiApp:
    """Subtap TUI 应用主类。"""

    def __init__(self):
        self.theme = Theme()
        self.reader = KeyReader()
        self._state = "home"
        self._state_stack: list[str] = []
        self.config = ConfigManager(Path.home() / ".subtap" / "config.yaml")

    def run(self) -> None:
        with self.reader:
            self._enter_alt_screen()
            try:
                self._event_loop()
            finally:
                self._leave_alt_screen()
                self.reader.restore_terminal()

    def _event_loop(self) -> None:
        while True:
            action = self._render_and_read()
            if action == "quit":
                break

    def _render_and_read(self) -> str:
        if self._state == "home":
            return self._view_home()
        elif self._state == "settings":
            return self._view_settings()
        elif self._state == "new_task":
            return self._view_new_task()
        elif self._state == "history":
            return self._view_history()
        elif self._state == "batch":
            return self._view_batch()
        elif self._state == "setup":
            return self._view_setup()
        return "quit"

    def _push_state(self, state: str) -> None:
        self._state_stack.append(self._state)
        self._state = state

    def _pop_state(self) -> None:
        if self._state_stack:
            self._state = self._state_stack.pop()
        else:
            self._state = "home"

    def _enter_alt_screen(self) -> None:
        if sys.stderr.isatty():
            sys.stderr.write("\033[?1049h")
            sys.stderr.flush()

    def _leave_alt_screen(self) -> None:
        if sys.stderr.isatty():
            sys.stderr.write("\033[?1049l")
            sys.stderr.flush()

    def _view_home(self) -> str:
        t = self.theme
        # Logo 作为 prefix，尾部空行提供 logo 和菜单之间的间距（5行）
        prefix = [
            f"{t.CYAN} ___      _    _             {t.NC}",
            f"{t.CYAN}/ __|_  _| |__| |_ __ _ _ __ {t.NC}",
            f"{t.CYAN}\\__ \\ || | '_ \\  _/ _` | '_ \\{t.NC}",
            f"{t.CYAN}|___/\\_,_|_.__/\\__\\__,_| .__/{t.NC}",
            f"{t.CYAN}                       |_|   {t.NC}",
            f"{t.GRAY}          音频转录工具{t.NC}",
            "", "", "", "", "",
        ]

        menu = Menu(
            title="",
            items=[
                "1. 新建转录    从音频/视频生成文字稿",
                "2. 转录历史    查看记录、重新保存",
                "3. 批量转录    一次处理多个文件",
                "4. 设置        模型、接口、偏好",
            ],
            footer="↑↓ 导航  Enter 确认  Q 退出",
            theme=self.theme,
            prefix_lines=prefix,
        )
        menu.render_full()
        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key in (Key.UP,):
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,):
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                selected = menu.cursor
                if selected == 0:
                    self._push_state("new_task")
                    return "continue"
                elif selected == 1:
                    self._push_state("history")
                    return "continue"
                elif selected == 2:
                    self._push_state("batch")
                    return "continue"
                elif selected == 3:
                    self._push_state("settings")
                    return "continue"
            elif key.startswith("CHAR:"):
                digit = key[5:]
                if digit.isdigit() and 1 <= int(digit) <= len(menu.items):
                    menu.cursor = int(digit) - 1
                    menu.render_incremental(old_cursor)
                continue

    def _view_settings(self) -> str:
        menu = Menu(
            title="设置",
            items=[
                "1. 语音识别    识别模型和语言",
                "2. 智能优化    自动纠错、专有名词、翻译",
                "3. 保存格式    SRT/ASS/VTT/JSON",
                "4. 在线服务    接口地址和密钥",
                "5. 语音模型    下载和管理",
            ],
            footer="↑↓ 导航  Enter 确认  Esc 返回  Q 退出",
            theme=self.theme,
        )
        menu.render_full()
        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)

    def _view_new_task(self) -> str:
        t = self.theme
        view = NewTaskView(config=self.config, home_dir=Path.home())
        picker = FilePicker(Path.home())
        items = picker.list_items()
        menu_items = [f"📁 {i.name}" if i.is_dir else i.name for i in items]
        if not menu_items:
            menu_items = ["(当前目录无音频/视频文件)"]

        menu = Menu(
            title="新建转录 · 选择文件",
            items=menu_items,
            footer="↑↓ 导航  Enter 选择  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                # 如果不在根目录，返回上级
                if picker.path != Path.home():
                    picker = picker.parent()
                    items = picker.list_items()
                    menu_items = [f"📁 {i.name}" if i.is_dir else i.name for i in items]
                    if not menu_items:
                        menu_items = ["(当前目录无音频/视频文件)"]
                    menu = Menu(
                        title=f"新建转录 · {picker.path.name or '/'}",
                        items=menu_items,
                        footer="↑↓ 导航  Enter 选择  Esc 返回",
                        theme=self.theme,
                    )
                    menu.render_full()
                else:
                    self._pop_state()
                    return "continue"
            elif key in (Key.UP,):
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,):
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                if not items:
                    continue
                selected = items[menu.cursor]
                if selected.is_dir:
                    picker = picker.enter(selected.name)
                    items = picker.list_items()
                    menu_items = [f"📁 {i.name}" if i.is_dir else i.name for i in items]
                    if not menu_items:
                        menu_items = ["(当前目录无音频/视频文件)"]
                    menu = Menu(
                        title=f"新建转录 · {picker.path.name or '/'}",
                        items=menu_items,
                        footer="↑↓ 导航  Enter 选择  Esc 返回",
                        theme=self.theme,
                    )
                    menu.render_full()
                else:
                    view.select_file(selected.path)
                    return self._view_confirm_run(view)

    def _view_confirm_run(self, view: NewTaskView) -> str:
        t = self.theme
        settings = view.get_confirm_settings()
        file_name = view.selected_file.name if view.selected_file else "未知"

        items = [
            f"文件：{file_name}",
            f"语言：{settings['language']}",
            f"格式：{settings['format']}",
        ]
        menu = Menu(
            title="确认转录",
            items=items,
            footer="Enter 开始转录  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.ENTER:
                return self._execute_run(view)

    def _execute_run(self, view: NewTaskView) -> str:
        t = self.theme
        cmd = view.build_run_command()
        if not cmd:
            self._pop_state()
            return "continue"

        sys.stderr.write("\033[2J\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}正在转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}文件：{view.selected_file.name}{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}请稍候...{t.NC}\r\n")
        sys.stderr.flush()

        result = subprocess.run(cmd, capture_output=True, text=True)

        sys.stderr.write("\033[2J\033[H")
        if result.returncode == 0:
            sys.stderr.write(f"\033[2K{t.GREEN}✓ 转录完成{t.NC}\r\n\r\n")
        else:
            sys.stderr.write(f"\033[2K{t.RED}✗ 转录失败{t.NC}\r\n\r\n")
            if result.stderr:
                sys.stderr.write(f"\033[2K{t.GRAY}{result.stderr[:200]}{t.NC}\r\n")
        sys.stderr.write(f"\033[2K\r\n{t.GRAY}Esc 返回{t.NC}\r\n")
        sys.stderr.flush()

        while True:
            key = self.reader.read_key(timeout=0.05)
            if key in (Key.ESCAPE, Key.ENTER):
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"

    def _view_history(self) -> str:
        t = self.theme
        scanner = HistoryScanner(Path.home() / ".subtap" / "history")
        records = scanner.scan()

        if not records:
            sys.stderr.write("\033[2J\033[H")
            sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}转录历史{t.NC}\r\n\r\n")
            sys.stderr.write(f"\033[2K{t.GRAY}暂无记录{t.NC}\r\n\r\n")
            sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
            sys.stderr.flush()
            while True:
                key = self.reader.read_key(timeout=0.05)
                if key in (Key.ESCAPE, Key.QUIT):
                    self._pop_state()
                    return "continue" if key == Key.ESCAPE else "quit"

        menu_items = []
        for r in records:
            status_icon = "✓" if r.is_completed else "✗"
            menu_items.append(f"{r.timestamp[:10]}  {r.input_name:<20} {r.duration_str:>8}  {status_icon}")

        menu = Menu(
            title="转录历史",
            items=menu_items,
            footer="↑↓ 导航  Enter 详情  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key in (Key.UP,):
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,):
                menu.move_down()
                menu.render_incremental(old_cursor)

    def _view_batch(self) -> str:
        t = self.theme
        sys.stderr.write("\033[2J\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}批量转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K  Enter 选择文件夹\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回  Q 退出{t.NC}\r\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.ENTER:
                # TODO: 文件夹选择
                pass

    def _view_setup(self) -> str:
        t = self.theme
        sys.stderr.write("\033[2J\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}欢迎使用 Subtap{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K  首次使用，需要完成基础配置\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Enter 开始配置  Q 退出{t.NC}\r\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ENTER:
                # TODO: 配置流程
                self._pop_state()
                return "continue"


def main():
    app = TuiApp()
    app.run()


if __name__ == "__main__":
    main()
