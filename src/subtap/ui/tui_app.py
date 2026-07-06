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
from .file_picker import FilePicker, AUDIO_VIDEO_EXTENSIONS
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
                "3. 保存设置    格式、字数、标点、双语",
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
            elif key == Key.ENTER:
                selected = menu.cursor
                if selected == 0:
                    return self._view_settings_asr()
                elif selected == 1:
                    return self._view_settings_enhance()
                elif selected == 2:
                    return self._view_settings_format()
                elif selected == 3:
                    return self._view_settings_api()
                elif selected == 4:
                    return self._view_settings_models()

    def _view_settings_asr(self) -> str:
        t = self.theme
        model = self.config.get("asr.model", "asr_0.6b")
        lang = self.config.get("output.subtitle_language", "zh")
        mode = self.config.get("mode", "offline")

        items = [
            f"模型：{model}",
            f"语言：{'中文' if lang == 'zh' else '英文' if lang == 'en' else '自动检测'}",
            f"模式：{'在线服务' if mode == 'online' else '本地运行'}",
        ]
        menu = Menu(title="设置 · 语音识别", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key in (Key.UP,):
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,):
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                if menu.cursor == 0:
                    models = ["asr_0.6b", "asr_1.7b"]
                    idx = models.index(model) if model in models else 0
                    model = models[(idx + 1) % len(models)]
                    self.config.set("asr.model", model)
                    self.config.save()
                elif menu.cursor == 1:
                    langs = [("zh", "中文"), ("en", "英文"), ("", "自动检测")]
                    idx = next((i for i, (k, _) in enumerate(langs) if k == lang), 0)
                    lang, _ = langs[(idx + 1) % len(langs)]
                    self.config.set("output.subtitle_language", lang)
                    self.config.save()
                elif menu.cursor == 2:
                    mode = "online" if mode == "offline" else "offline"
                    self.config.set("mode", mode)
                    self.config.save()
                items[0] = f"模型：{model}"
                items[1] = f"语言：{'中文' if lang == 'zh' else '英文' if lang == 'en' else '自动检测'}"
                items[2] = f"模式：{'在线服务' if mode == 'online' else '本地运行'}"
                menu = Menu(title="设置 · 语音识别", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
                menu.render_full()

    def _view_settings_enhance(self) -> str:
        t = self.theme
        proofread = self.config.get("llm_proofread", False)
        hotword = self.config.get("llm_hotword", False)
        translate = self.config.get("translate_to", "")
        # 热词列表
        hotwords_path = Path.home() / ".subtap" / "glossary" / "hotwords_zh.txt"
        hotwords_list = []
        if hotwords_path.exists():
            for line in hotwords_path.read_text(encoding="utf-8").strip().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    hotwords_list.append(line)

        nonlocal_vars = {"proofread": proofread, "hotword": hotword, "translate": translate}

        def get_items():
            p = nonlocal_vars["proofread"]
            h = nonlocal_vars["hotword"]
            tr = nonlocal_vars["translate"]
            hw_count = len(hotwords_list)
            return [
                f"自动纠错：{'开启' if p else '关闭'}",
                f"专有名词：{'开启' if h else '关闭'}",
                f"热词列表：{hw_count} 个词" if hw_count > 0 else "热词列表：未配置",
                f"自动翻译：{'关闭' if not tr else tr}",
            ]

        items = get_items()
        menu = Menu(title="设置 · 智能优化", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key in (Key.UP,):
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,):
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                if menu.cursor == 0:
                    nonlocal_vars["proofread"] = not nonlocal_vars["proofread"]
                    self.config.set("llm_proofread", nonlocal_vars["proofread"])
                    self.config.save()
                elif menu.cursor == 1:
                    nonlocal_vars["hotword"] = not nonlocal_vars["hotword"]
                    self.config.set("llm_hotword", nonlocal_vars["hotword"])
                    self.config.save()
                elif menu.cursor == 2:
                    # 热词列表查看（只读）
                    self._view_hotword_list(hotwords_list)
                    # 返回后重新渲染
                elif menu.cursor == 3:
                    targets = [("", "关闭"), ("en", "英文"), ("ja", "日文")]
                    idx = next((i for i, (k, _) in enumerate(targets) if k == nonlocal_vars["translate"]), 0)
                    nonlocal_vars["translate"], _ = targets[(idx + 1) % len(targets)]
                    self.config.set("translate_to", nonlocal_vars["translate"])
                    self.config.save()
                items = get_items()
                menu = Menu(title="设置 · 智能优化", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
                menu.render_full()

    def _view_hotword_list(self, hotwords: list[str]) -> None:
        """热词列表查看（只读）。"""
        t = self.theme
        if not hotwords:
            items = ["暂无热词，使用过程中会自动学习"]
        else:
            items = hotwords[:50]  # 最多显示 50 个
            if len(hotwords) > 50:
                items.append(f"... 还有 {len(hotwords) - 50} 个")
        menu = Menu(
            title="热词列表",
            items=items,
            footer="↑↓ 导航  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()
        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key in (Key.ESCAPE,):
                return
            elif key == Key.QUIT:
                return
            elif key in (Key.UP,) and items:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,) and items:
                menu.move_down()
                menu.render_incremental(old_cursor)

    def _view_settings_format(self) -> str:
        t = self.theme
        fmts = self.config.get("output.subtitle_formats", ["srt"])
        max_chars = self.config.get("output.max_chars", 25)
        min_chars = self.config.get("output.min_chars", 10)
        punctuation = self.config.get("output.subtitle_punctuation", False)
        bilingual = self.config.get("output.bilingual", "off")

        nonlocal_vars = {
            "fmts": fmts, "max_chars": max_chars, "min_chars": min_chars,
            "punctuation": punctuation, "bilingual": bilingual,
        }

        def get_items():
            v = nonlocal_vars
            bi_map = {"off": "关闭", "source-first": "原文优先", "target-first": "译文优先"}
            return [
                f"字幕格式：{', '.join(f.upper() for f in v['fmts'])}",
                f"每行最大字数：{v['max_chars']}",
                f"每行最小字数：{v['min_chars']}",
                f"标点符号：{'开启' if v['punctuation'] else '关闭'}",
                f"双语字幕：{bi_map.get(v['bilingual'], '关闭')}",
            ]

        items = get_items()
        menu = Menu(title="设置 · 保存设置", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key in (Key.ESCAPE,):
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key in (Key.UP,):
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,):
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                if menu.cursor == 0:
                    all_fmts = [["srt"], ["vtt"], ["json"], ["tsv"]]
                    idx = next((i for i, f in enumerate(all_fmts) if f == nonlocal_vars["fmts"]), 0)
                    nonlocal_vars["fmts"] = all_fmts[(idx + 1) % len(all_fmts)]
                    self.config.set("output.subtitle_formats", nonlocal_vars["fmts"])
                elif menu.cursor == 1:
                    nonlocal_vars["max_chars"] = 15 if nonlocal_vars["max_chars"] >= 60 else nonlocal_vars["max_chars"] + 5
                    self.config.set("output.max_chars", nonlocal_vars["max_chars"])
                elif menu.cursor == 2:
                    nonlocal_vars["min_chars"] = 4 if nonlocal_vars["min_chars"] >= 30 else nonlocal_vars["min_chars"] + 2
                    self.config.set("output.min_chars", nonlocal_vars["min_chars"])
                elif menu.cursor == 3:
                    nonlocal_vars["punctuation"] = not nonlocal_vars["punctuation"]
                    self.config.set("output.subtitle_punctuation", nonlocal_vars["punctuation"])
                elif menu.cursor == 4:
                    modes = ["off", "source-first", "target-first"]
                    idx = modes.index(nonlocal_vars["bilingual"]) if nonlocal_vars["bilingual"] in modes else 0
                    nonlocal_vars["bilingual"] = modes[(idx + 1) % len(modes)]
                    self.config.set("output.bilingual", nonlocal_vars["bilingual"])
                self.config.save()
                items = get_items()
                menu = Menu(title="设置 · 保存设置", items=items, footer="↑↓ 导航  Enter 切换  Esc 返回", theme=self.theme)
                menu.render_full()

    def _view_settings_api(self) -> str:
        t = self.theme
        base_url = self.config.get("remote_api.base_url", "未配置")
        has_key = bool(self.config.get("remote_api.api_key_env"))

        nonlocal_vars = {"base_url": base_url, "has_key": has_key}

        def get_items():
            return [
                f"接口地址：{nonlocal_vars['base_url']}",
                f"密钥：{'已配置' if nonlocal_vars['has_key'] else '未配置'}",
            ]

        items = get_items()
        menu = Menu(title="设置 · 在线服务", items=items, footer="↑↓ 导航  Enter 修改  Esc 返回", theme=self.theme)
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key in (Key.ESCAPE,):
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key in (Key.UP,):
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key in (Key.DOWN,):
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                # 退出 alt screen，用 questionary 输入
                self._leave_alt_screen()
                self.reader.restore_terminal()
                try:
                    try:
                        import questionary
                    except ImportError:
                        sys.stderr.write("\033[H\033[J")
                        sys.stderr.write(f"\033[2K{t.RED}需要安装 questionary：pip install questionary{t.NC}\r\n")
                        sys.stderr.flush()
                        import time; time.sleep(2)
                        raise
                    if menu.cursor == 0:
                        url = questionary.text("请输入接口地址：", default=nonlocal_vars["base_url"]).ask()
                        if url:
                            nonlocal_vars["base_url"] = url
                            self.config.set("remote_api.base_url", url)
                            self.config.save()
                    elif menu.cursor == 1:
                        key_val = questionary.password("请输入访问密钥：").ask()
                        if key_val:
                            self.config.set("remote_api.api_key_env", key_val)
                            nonlocal_vars["has_key"] = True
                            self.config.save()
                except Exception as e:
                    # questionary 操作被取消或出错，显示简短提示
                    sys.stderr.write(f"\033[H\033[J")
                    sys.stderr.write(f"\033[2K{t.RED}操作取消：{e}{t.NC}\r\n")
                    sys.stderr.flush()
                finally:
                    self.reader.setup_terminal()
                    self._enter_alt_screen()
                items = get_items()
                menu = Menu(title="设置 · 在线服务", items=items, footer="↑↓ 导航  Enter 修改  Esc 返回", theme=self.theme)
                menu.render_full()

    def _view_settings_models(self) -> str:
        t = self.theme
        items = ["模型管理功能开发中..."]
        menu = Menu(title="设置 · 语音模型", items=items, footer="Esc 返回", theme=self.theme)
        menu.render_full()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key in (Key.ESCAPE,):
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"

    def _view_new_task(self) -> str:
        t = self.theme
        view = NewTaskView(config=self.config, home_dir=Path.home())

        # 显示拖入提示
        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}新建转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K  拖入音频或视频文件到此处，按 Enter 确认\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}支持格式：mp3, wav, m4a, mp4, mkv, avi...{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回主菜单{t.NC}\r\n")
        sys.stderr.flush()

        # 直接读取原始字节，不用 read_key() 的解码逻辑
        # 避免 UTF-8 多字节字符被逐字节解码导致乱码
        raw_buf = b""

        while True:
            byte = self.reader._read_byte(timeout=0.1)
            if byte is None:
                continue
            # Enter: \r 或 \n
            if byte in (b"\r", b"\n"):
                if raw_buf:
                    try:
                        path_str = raw_buf.decode("utf-8")
                    except UnicodeDecodeError:
                        path_str = raw_buf.decode("utf-8", errors="replace")
                    clean_path = path_str.strip().strip("'\"")
                    file_path = Path(clean_path).expanduser()
                    if not file_path.is_file():
                        sys.stderr.write(f"\033[8;1H\033[2K{t.RED}文件不存在：{clean_path}{t.NC}\r\n")
                        sys.stderr.flush()
                        raw_buf = b""
                    elif file_path.suffix.lower() not in AUDIO_VIDEO_EXTENSIONS:
                        sys.stderr.write(f"\033[8;1H\033[2K{t.RED}不支持的格式：{file_path.suffix}{t.NC}\r\n")
                        sys.stderr.flush()
                        raw_buf = b""
                    else:
                        view.select_file(file_path)
                        return self._view_confirm_run(view)
            # Esc: 0x1b
            elif byte == b"\x1b":
                self._pop_state()
                return "continue"
            # Ctrl+C: 0x03
            elif byte == b"\x03":
                return "quit"
            # Backspace/Delete: 0x7f 或 0x08
            elif byte in (b"\x7f", b"\x08"):
                if raw_buf:
                    raw_buf = raw_buf[:-1]
                    while raw_buf and (raw_buf[-1] & 0xC0) == 0x80:
                        raw_buf = raw_buf[:-1]
                    self._update_path_display(raw_buf)
            # Ctrl+U: 清空
            elif byte == b"\x15":
                raw_buf = b""
                self._update_path_display(raw_buf)
            # 其他字节：直接追加（包括中文 UTF-8 多字节）
            else:
                raw_buf += byte
                self._update_path_display(raw_buf)

    def _update_path_display(self, raw_buf: bytes) -> None:
        t = self.theme
        try:
            display = raw_buf.decode("utf-8")
        except UnicodeDecodeError:
            display = raw_buf.decode("utf-8", errors="replace")
        display = display[-60:] if len(display) > 60 else display
        sys.stderr.write(f"\033[6;1H\033[2K{t.CYAN}> {display}{t.NC}")
        sys.stderr.flush()

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

        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}正在转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}文件：{view.selected_file.name}{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}请稍候...{t.NC}\r\n")
        sys.stderr.flush()

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        except subprocess.TimeoutExpired:
            sys.stderr.write("\033[H\033[J")
            sys.stderr.write(f"\033[2K{t.RED}✗ 转录超时（超过1小时）{t.NC}\r\n")
            sys.stderr.write(f"\033[2K\r\n{t.GRAY}Esc 返回{t.NC}\r\n")
            sys.stderr.flush()
            while True:
                key = self.reader.read_key(timeout=0.05)
                if key in (Key.ESCAPE, Key.ENTER):
                    self._pop_state()
                    return "continue"
                elif key == Key.QUIT:
                    return "quit"
        except FileNotFoundError:
            sys.stderr.write("\033[H\033[J")
            sys.stderr.write(f"\033[2K{t.RED}✗ 未找到 subtap 命令{t.NC}\r\n")
            sys.stderr.write(f"\033[2K\r\n{t.GRAY}Esc 返回{t.NC}\r\n")
            sys.stderr.flush()
            while True:
                key = self.reader.read_key(timeout=0.05)
                if key in (Key.ESCAPE, Key.ENTER):
                    self._pop_state()
                    return "continue"
                elif key == Key.QUIT:
                    return "quit"

        sys.stderr.write("\033[H\033[J")
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
            sys.stderr.write("\033[H\033[J")
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

        # 显示拖入提示
        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}批量转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K  拖入文件夹到此处，按 Enter 确认\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}将处理文件夹中所有音频/视频文件{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回主菜单{t.NC}\r\n")
        sys.stderr.flush()

        # 直接读取原始字节，不用 read_key() 的解码逻辑
        raw_buf = b""

        while True:
            byte = self.reader._read_byte(timeout=0.1)
            if byte is None:
                continue
            if byte in (b"\r", b"\n"):
                if raw_buf:
                    try:
                        path_str = raw_buf.decode("utf-8")
                    except UnicodeDecodeError:
                        path_str = raw_buf.decode("utf-8", errors="replace")
                    clean_path = path_str.strip().strip("'\"")
                    folder = Path(clean_path).expanduser()
                    if not folder.is_dir():
                        sys.stderr.write(f"\033[8;1H\033[2K{t.RED}文件夹不存在：{clean_path}{t.NC}\r\n")
                        sys.stderr.flush()
                        raw_buf = b""
                    else:
                        return self._execute_batch(folder)
            elif byte == b"\x1b":
                self._pop_state()
                return "continue"
            elif byte == b"\x03":
                return "quit"
            elif byte in (b"\x7f", b"\x08"):
                if raw_buf:
                    raw_buf = raw_buf[:-1]
                    while raw_buf and (raw_buf[-1] & 0xC0) == 0x80:
                        raw_buf = raw_buf[:-1]
                    self._update_path_display(raw_buf)
            elif byte == b"\x15":
                raw_buf = b""
                self._update_path_display(raw_buf)
            else:
                raw_buf += byte
                self._update_path_display(raw_buf)

    def _execute_batch(self, folder: Path) -> str:
        t = self.theme
        audio_files = sorted([f for f in folder.iterdir() if f.suffix.lower() in AUDIO_VIDEO_EXTENSIONS])

        if not audio_files:
            sys.stderr.write("\033[H\033[J")
            sys.stderr.write(f"\033[2K{t.RED}该文件夹中无音频/视频文件{t.NC}\r\n\r\n")
            sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
            sys.stderr.flush()
            while True:
                key = self.reader.read_key(timeout=0.05)
                if key in (Key.ESCAPE, Key.QUIT):
                    self._pop_state()
                    return "continue" if key == Key.ESCAPE else "quit"

        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}批量转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}文件夹：{folder}{t.NC}\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}文件数：{len(audio_files)}{t.NC}\r\n\r\n")
        sys.stderr.flush()

        completed = 0
        for i, f in enumerate(audio_files):
            sys.stderr.write(f"\033[{5 + i};1H\033[2K  ⠙ {f.name}")
            sys.stderr.flush()
            result = subprocess.run(["subtap", "run", str(f)], capture_output=True, text=True)
            if result.returncode == 0:
                completed += 1
                sys.stderr.write(f"\033[{5 + i};1H\033[2K  {t.GREEN}✓{t.NC} {f.name}")
            else:
                sys.stderr.write(f"\033[{5 + i};1H\033[2K  {t.RED}✗{t.NC} {f.name}")
            sys.stderr.flush()

        sys.stderr.write(f"\033[{5 + len(audio_files) + 1};1H\r\n")
        sys.stderr.write(f"\033[2K{t.GREEN}完成：{completed}/{len(audio_files)}{t.NC}\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
        sys.stderr.flush()

        while True:
            key = self.reader.read_key(timeout=0.05)
            if key in (Key.ESCAPE, Key.ENTER):
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"


def main():
    app = TuiApp()
    app.run()


if __name__ == "__main__":
    main()
