"""TUI 主入口，页面路由状态机。

用 ANSI 原生渲染实现交互式终端 UI。
"""
import os
import sys
from .keyboard import Key, KeyReader
from .theme import Theme
from .menu import Menu
from .spinner import Spinner


class TuiApp:
    """Subtap TUI 应用主类。"""

    def __init__(self):
        self.theme = Theme()
        self.reader = KeyReader()
        self._state = "home"
        self._state_stack: list[str] = []

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
        # Logo 占 3 行
        logo_lines = [
            f"\033[1;1H\033[2K{t.CYAN}  ____        _       {t.NC}",
            f"\033[2;1H\033[2K{t.CYAN} / ___| _   _| |_ __ _| |__   __ _ _ __  {t.NC}",
            f"\033[3;1H\033[2K{t.CYAN} \\___ \\| | | | __/ _` | '_ \\ / _` | '__| {t.NC}",
            f"\033[4;1H\033[2K{t.CYAN}  ___) | |_| | || (_| | |_) | (_| | |    {t.NC}",
            f"\033[5;1H\033[2K{t.CYAN} |____/ \\__, |\\__\\__,_|_.__/ \\__,_|_|    {t.NC}",
            f"\033[6;1H\033[2K{t.CYAN}        |___/  {t.GRAY}音频转录工具{t.NC}",
        ]
        sys.stderr.write("".join(logo_lines))
        sys.stderr.flush()

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
            offset=6,  # Logo 占 6 行
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
        sys.stderr.write("\033[2J\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}新建转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K  Enter 选择音频或视频文件\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}支持格式：mp3, wav, m4a, mp4, mkv, avi{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Enter 选择文件  Esc 返回  Q 退出{t.NC}\r\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.ENTER:
                # TODO: 文件选择对话框
                pass

    def _view_history(self) -> str:
        t = self.theme
        sys.stderr.write("\033[2J\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}转录历史{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}暂无记录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回  Q 退出{t.NC}\r\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                self._pop_state()
                return "continue"

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
