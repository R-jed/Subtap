"""TUI 主入口，页面路由状态机。

用 ANSI 原生渲染实现交互式终端 UI。
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from .keyboard import Key, KeyReader
from .theme import Theme
from .menu import Menu
from .config_manager import ConfigManager
from .file_picker import AUDIO_VIDEO_EXTENSIONS
from .views.new_task import NewTaskView
from .views.wizard import WizardView
from .history import HistoryScanner

KEY_READ_TIMEOUT = 0.05


def _run_env() -> dict[str, str]:
    """返回带 PYTHONPATH 的环境变量，支持从源码直接运行。"""
    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parent.parent.parent)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing}" if existing else src_dir
    return env


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
        elif self._state == "first_run":
            return self._view_first_run()
        elif self._state == "wizard":
            return self._view_wizard()
        elif self._state == "glossary_page":
            return self._view_glossary_page()
        elif self._state == "manuscripts_page":
            return self._view_manuscripts_page()
        elif self._state == "recent_tasks":
            return self._view_recent_tasks()
        elif self._state == "models_page":
            return self._view_models_page()
        elif self._state == "completion":
            return self._view_completion()
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
            sys.stderr.write("\033[?1049l\033[?25h")
            sys.stderr.flush()

    def _view_home(self) -> str:
        from .views.home import HomeView

        home = HomeView()

        # First run check
        if home.is_first_run():
            self._push_state("first_run")
            return "continue"

        prefix = home.build_prefix_lines()
        menu = Menu(
            title="",
            items=home.build_menu_items(),
            footer="↑↓ 导航  Enter 确认  Q 退出",
            theme=self.theme,
            prefix_lines=prefix,
        )
        menu.render_full()
        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                state = home.map_selection_to_state(menu.cursor)
                if state:
                    self._push_state(state)
                    return "continue"
            elif key.startswith("CHAR:"):
                digit = key[5:]
                if digit.isdigit() and 1 <= int(digit) <= len(menu.items):
                    menu.cursor = int(digit) - 1
                    menu.render_incremental(old_cursor)
                continue

    def _view_first_run(self) -> str:
        from .views.first_run import FirstRunView

        t = self.theme
        view = FirstRunView()

        def _clear():
            sys.stderr.write("\033[H\033[J")
            sys.stderr.flush()

        def _line(row: int, text: str):
            sys.stderr.write(f"\033[{row};1H\033[2K{text}")
            sys.stderr.flush()

        # Step 1: Welcome
        _clear()
        _line(1, f"{t.CYAN}[1/7] 欢迎使用 Subtap{t.NC}")
        _line(3, "首次启动需要完成简单配置。")
        _line(5, f"{t.GRAY}按任意键继续...{t.NC}")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

        # Step 2: Device check
        _clear()
        _line(1, f"{t.CYAN}[2/7] 设备检查{t.NC}")
        _line(3, "正在检测设备信息...")
        sys.stderr.flush()
        device = view.check_device()
        _line(3, f"  Apple Silicon：{'是' if device['is_apple_silicon'] else '否'}")
        _line(4, f"  ffmpeg：{'已安装' if device['has_ffmpeg'] else '未安装'}")
        _line(5, f"  MLX：{'可用' if device['has_mlx'] else '不可用'}")
        _line(6, f"  内存：{device['memory_gb']:.1f} GB")
        _line(7, f"  可用磁盘：{device['free_gb']:.1f} GB")
        _line(9, f"{t.GRAY}按任意键继续...{t.NC}")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

        # Step 3: Model recommendation
        _clear()
        _line(1, f"{t.CYAN}[3/7] 模型推荐{t.NC}")
        runtime_ok = (
            device["is_apple_silicon"] and device["has_ffmpeg"] and device["has_mlx"]
        )
        fast_ok = runtime_ok and device["free_gb"] > 2
        quality_ok = fast_ok and device["memory_gb"] >= 16 and device["free_gb"] > 5
        if not fast_ok:
            _line(
                3, f"{t.RED}设备未满足本地离线运行要求，请根据上一步修复后重试。{t.NC}"
            )
            _line(5, f"{t.GRAY}按任意键返回...{t.NC}")
            self.reader.read_key(timeout=60)
            return "continue"
        model_name = view.recommend_model(fast_ok=fast_ok, quality_ok=quality_ok)
        _line(3, f"推荐模型：{t.GREEN}{model_name}{t.NC}")
        if quality_ok:
            _line(4, f"{t.GRAY}设备性能充足，推荐高质量模型{t.NC}")
        else:
            _line(4, f"{t.GRAY}设备条件有限，推荐轻量模型{t.NC}")
        _line(6, f"{t.GRAY}按任意键继续...{t.NC}")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

        # Step 4: Download info
        _clear()
        _line(1, f"{t.CYAN}[4/7] 下载信息{t.NC}")
        info = view.get_download_info(model_name)
        _line(3, f"模型：{info['model_name']}")
        _line(4, f"大小：{info['size_display']}")
        _line(5, f"路径：{info['target_dir']}")
        _line(6, f"预计耗时：约 {info['estimated_seconds']} 秒（按 10 MB/s）")
        _line(7, f"{t.GRAY}按任意键继续...{t.NC}")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

        # Step 5: Confirm download
        _clear()
        _line(1, f"{t.CYAN}[5/7] 确认下载{t.NC}")
        _line(3, f"即将下载模型 {t.GREEN}{model_name}{t.NC}（{info['size_display']}）")
        _line(5, "Y 确认下载  N 跳过")
        sys.stderr.flush()

        confirmed = False
        while True:
            key = self.reader.read_key(timeout=60)
            if key is None:
                continue
            if key == "CHAR:Y" or key == "CHAR:y":
                confirmed = True
                break
            if key in ("CHAR:N", "CHAR:n", Key.ESCAPE):
                break

        # Step 6: Download and minimal offline verification
        _clear()
        _line(1, f"{t.CYAN}[6/7] 下载模型{t.NC}")
        if not confirmed:
            _line(3, f"{t.YELLOW}尚未完成模型安装，初始化不会标记为完成。{t.NC}")
            _line(5, f"{t.GRAY}按任意键返回...{t.NC}")
            self.reader.read_key(timeout=60)
            return "continue"

        config = self.config.to_subtap_config()
        sources = ("hf", "hf-mirror", "modelscope")
        source_index = 0
        while True:
            try:
                from subtap.core.models import ModelDownloader

                downloader = ModelDownloader(config)
                downloader.download(model_name, source=sources[source_index])
                view.run_offline_self_check(config, model_name)
                _line(3, f"{t.GREEN}✓ 模型下载及离线自检完成{t.NC}")
                break
            except Exception as e:
                _line(3, f"{t.RED}下载失败：{e}{t.NC}")
                _line(5, "R 重试  S 切换下载源  D 查看详情  Esc 返回")
                while True:
                    key = self.reader.read_key(timeout=60)
                    if key in ("CHAR:R", "CHAR:r"):
                        break
                    if key in ("CHAR:S", "CHAR:s"):
                        source_index = (source_index + 1) % len(sources)
                        _line(6, f"已切换到：{sources[source_index]}")
                        break
                    if key in ("CHAR:D", "CHAR:d"):
                        _line(7, f"{type(e).__name__}: {e}")
                    if key == Key.ESCAPE:
                        return "continue"
        _line(6, f"{t.GRAY}按任意键继续...{t.NC}")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

        # Step 7: Completion
        _clear()
        _line(1, f"{t.GREEN}[7/7] 配置完成{t.NC}")
        _line(3, "初始化向导已完成！")
        _line(5, f"{t.GRAY}按任意键进入主界面...{t.NC}")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

        from subtap.core.state_store import StateStore

        state_path = view.mark_complete()
        store = StateStore(state_path)
        store.load()  # creates with first_run_time
        self._pop_state()
        return "continue"

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
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                    return self._view_models_page()

    def _view_settings_asr(self) -> str:
        model = self.config.get("asr.model", "asr_0.6b")
        lang = self.config.get("output.subtitle_language", "zh")
        mode = self.config.get("mode", "offline")

        items = [
            f"模型：{model}",
            f"语言：{'中文' if lang == 'zh' else '英文' if lang == 'en' else '自动检测'}",
            f"模式：{'在线服务' if mode == 'online' else '本地运行'}",
        ]
        menu = Menu(
            title="设置 · 语音识别",
            items=items,
            footer="↑↓ 导航  Enter 切换  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                items[1] = (
                    f"语言：{'中文' if lang == 'zh' else '英文' if lang == 'en' else '自动检测'}"
                )
                items[2] = f"模式：{'在线服务' if mode == 'online' else '本地运行'}"
                menu = Menu(
                    title="设置 · 语音识别",
                    items=items,
                    footer="↑↓ 导航  Enter 切换  Esc 返回",
                    theme=self.theme,
                )
                menu.render_full()

    def _view_settings_enhance(self) -> str:
        proofread = self.config.get("llm_proofread", False)
        hotword = self.config.get("llm_hotword", False)
        translate = self.config.get("translate_to", "")
        # 热词列表
        hotwords_path = Path.home() / ".subtap" / "glossaries" / "default.yaml"
        hotwords_list = []
        if hotwords_path.exists():
            for line in hotwords_path.read_text(encoding="utf-8").strip().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    hotwords_list.append(line)

        nonlocal_vars = {
            "proofread": proofread,
            "hotword": hotword,
            "translate": translate,
        }

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
        menu = Menu(
            title="设置 · 智能优化",
            items=items,
            footer="↑↓ 导航  Enter 切换  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                    idx = next(
                        (
                            i
                            for i, (k, _) in enumerate(targets)
                            if k == nonlocal_vars["translate"]
                        ),
                        0,
                    )
                    nonlocal_vars["translate"], _ = targets[(idx + 1) % len(targets)]
                    self.config.set("translate_to", nonlocal_vars["translate"])
                    self.config.save()
                items = get_items()
                menu = Menu(
                    title="设置 · 智能优化",
                    items=items,
                    footer="↑↓ 导航  Enter 切换  Esc 返回",
                    theme=self.theme,
                )
                menu.render_full()

    def _view_hotword_list(self, hotwords: list[str]) -> None:
        """热词列表查看（只读）。"""
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
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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

    def _view_glossary_page(self) -> str:
        from .views.glossary_page import GlossaryPage
        from subtap.glossary.hotword import load_glossary, save_glossary

        t = self.theme
        page = GlossaryPage()
        glossary_path = Path.home() / ".subtap" / "glossaries" / "default.yaml"
        glossary = load_glossary(glossary_path, "zh")
        items = page.build_glossary_items(glossary.hotwords)

        menu = Menu(
            title="热词库",
            items=items,
            footer="↑↓ 导航  A 添加  D 删除  E 编辑  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == "CHAR:A" or key == "CHAR:a":
                sys.stderr.write("\033[2J\033[H")
                sys.stderr.write(f"{t.CYAN}添加热词{t.NC}\n\n")
                sys.stderr.write("热词名称（直接回车取消）：")
                word = input().strip()
                if word:
                    sys.stderr.write("别名（逗号分隔，直接回车跳过）：")
                    aliases_raw = input().strip()
                    aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
                    existing = {hw.word for hw in glossary.hotwords}
                    if word in existing:
                        sys.stderr.write(f"\n{t.YELLOW}热词 '{word}' 已存在{t.NC}\n")
                    else:
                        from subtap.glossary.hotword import Hotword

                        glossary.add(Hotword(word=word, aliases=aliases))
                        save_glossary(glossary, glossary_path)
                        items = page.build_glossary_items(glossary.hotwords)
                        menu = Menu(
                            title="热词库",
                            items=items,
                            footer="↑↓ 导航  A 添加  D 删除  E 编辑  Esc 返回",
                            theme=self.theme,
                        )
                        sys.stderr.write(f"\n{t.GREEN}✓ 已添加 '{word}'{t.NC}\n")
                menu.render_full()
            elif key == "CHAR:D" or key == "CHAR:d":
                if glossary.hotwords and menu.cursor < len(glossary.hotwords):
                    hw = glossary.hotwords[menu.cursor]
                    sys.stderr.write(f"\n{t.YELLOW}确认删除 '{hw.word}'？(Y/N){t.NC} ")
                    confirm = input().strip().upper()
                    if confirm == "Y":
                        glossary.remove(hw.word)
                        save_glossary(glossary, glossary_path)
                        items = page.build_glossary_items(glossary.hotwords)
                        menu = Menu(
                            title="热词库",
                            items=items,
                            footer="↑↓ 导航  A 添加  D 删除  E 编辑  Esc 返回",
                            theme=self.theme,
                        )
                    menu.render_full()
            elif key == "CHAR:E" or key == "CHAR:e":
                if glossary.hotwords and menu.cursor < len(glossary.hotwords):
                    hw = glossary.hotwords[menu.cursor]
                    sys.stderr.write(f"\n{t.CYAN}编辑 '{hw.word}'{t.NC}\n")
                    sys.stderr.write(f"当前别名：{', '.join(hw.aliases)}\n")
                    sys.stderr.write("新别名（逗号分隔，直接回车保留）：")
                    aliases_raw = input().strip()
                    if aliases_raw:
                        hw.aliases = [
                            a.strip() for a in aliases_raw.split(",") if a.strip()
                        ]
                        save_glossary(glossary, glossary_path)
                        items = page.build_glossary_items(glossary.hotwords)
                        menu = Menu(
                            title="热词库",
                            items=items,
                            footer="↑↓ 导航  A 添加  D 删除  E 编辑  Esc 返回",
                            theme=self.theme,
                        )
                    menu.render_full()

    def _view_manuscripts_page(self) -> str:
        from .views.manuscripts_page import ManuscriptsPage
        from subtap.core.manuscript_index import ManuscriptIndex

        page = ManuscriptsPage()
        index = ManuscriptIndex(Path.home() / ".subtap" / "manuscripts" / "index.json")
        manuscripts = index.list_all()
        items = page.build_items(manuscripts)

        menu = Menu(
            title="文稿库",
            items=items,
            footer="↑↓ 导航  A 添加  D 删除  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == "CHAR:A" or key == "CHAR:a":
                t = self.theme
                sys.stderr.write("\033[2J\033[H")
                sys.stderr.write(f"{t.CYAN}添加文稿{t.NC}\n\n")
                sys.stderr.write("文稿文件路径（直接回车取消）：")
                path_str = input().strip()
                if path_str:
                    doc_path = Path(path_str).expanduser()
                    if doc_path.exists():
                        index.add(doc_path.stem, str(doc_path))
                        manuscripts = index.list_all()
                        items = page.build_items(manuscripts)
                        menu = Menu(
                            title="文稿库",
                            items=items,
                            footer="↑↓ 导航  A 添加  D 删除  Esc 返回",
                            theme=self.theme,
                        )
                        sys.stderr.write(
                            f"\n{t.GREEN}✓ 已添加 '{doc_path.name}'{t.NC}\n"
                        )
                    else:
                        sys.stderr.write(f"\n{t.RED}文件不存在：{path_str}{t.NC}\n")
                menu.render_full()
            elif key == "CHAR:D" or key == "CHAR:d":
                if manuscripts and menu.cursor < len(manuscripts):
                    name = manuscripts[menu.cursor]["name"]
                    index.remove(name)
                    manuscripts = index.list_all()
                    items = page.build_items(manuscripts)
                    menu = Menu(
                        title="文稿库",
                        items=items,
                        footer="↑↓ 导航  A 添加  D 删除  Esc 返回",
                        theme=self.theme,
                    )
                    menu.render_full()

    def _view_recent_tasks(self) -> str:
        from .views.recent_tasks import RecentTasksPage
        from subtap.core.state_store import StateStore

        page = RecentTasksPage()
        store = StateStore(Path.home() / ".subtap" / "state.json")
        tasks = store.load().recent_tasks
        items = page.build_items(tasks)

        menu = Menu(
            title="最近任务",
            items=items,
            footer="↑↓ 导航  Enter 详情  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                if tasks and menu.cursor < len(tasks):
                    task = tasks[menu.cursor]
                    detail = [
                        f"任务ID：{task.get('task_id', '?')}",
                        f"输入文件：{task.get('input_name', '?')}",
                        f"输出路径：{task.get('output_path', '?')}",
                    ]
                    self._show_detail(detail)
                    menu.render_full()

    def _view_completion(self) -> str:
        from .views.completion import CompletionPage

        t = self.theme
        page = CompletionPage()

        # Read completion data from ui_state
        ui = self.config.get("ui_state", {})
        output_path = ui.get("last_output_path", "未知")
        duration_sec = ui.get("last_duration_sec", 0)

        info_items = page.build_items(output_path, duration_sec)[:3]
        actions = page.get_actions()

        # Render info lines statically, then show action menu
        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}转录完成{t.NC}\r\n\r\n")
        for line in info_items:
            sys.stderr.write(f"\033[2K{line}\r\n")
        sys.stderr.flush()

        menu = Menu(
            title="",
            items=actions,
            footer="↑↓ 导航  Enter 确认  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                selected = actions[menu.cursor]
                if selected == "打开字幕":
                    try:
                        subprocess.run(["open", output_path], check=True)
                    except subprocess.CalledProcessError as e:
                        sys.stderr.write(f"{t.RED}打开失败：{e}{t.NC}\n")
                    menu.render_full()
                elif selected == "打开输出目录":
                    try:
                        subprocess.run(
                            ["open", str(Path(output_path).parent)], check=True
                        )
                    except subprocess.CalledProcessError as e:
                        sys.stderr.write(f"{t.RED}打开失败：{e}{t.NC}\n")
                    menu.render_full()
                elif selected == "返回":
                    self._pop_state()
                    return "continue"
                else:
                    # 重新生成 / 处理另一个文件 → 回到主界面
                    self._pop_state()
                    return "continue"

    def _view_settings_format(self) -> str:
        fmts = self.config.get("output.subtitle_formats", ["srt"])
        max_chars = self.config.get("output.max_chars", 25)
        min_chars = self.config.get("output.min_chars", 10)
        punctuation = self.config.get("output.subtitle_punctuation", False)
        bilingual = self.config.get("output.bilingual", "off")

        nonlocal_vars = {
            "fmts": fmts,
            "max_chars": max_chars,
            "min_chars": min_chars,
            "punctuation": punctuation,
            "bilingual": bilingual,
        }

        def get_items():
            v = nonlocal_vars
            bi_map = {
                "off": "关闭",
                "source-first": "原文优先",
                "target-first": "译文优先",
            }
            return [
                f"字幕格式：{', '.join(f.upper() for f in v['fmts'])}",
                f"每行最大字数：{v['max_chars']}",
                f"每行最小字数：{v['min_chars']}",
                f"标点符号：{'开启' if v['punctuation'] else '关闭'}",
                f"双语字幕：{bi_map.get(v['bilingual'], '关闭')}",
            ]

        items = get_items()
        menu = Menu(
            title="设置 · 保存设置",
            items=items,
            footer="↑↓ 导航  Enter 切换  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                    idx = next(
                        (
                            i
                            for i, f in enumerate(all_fmts)
                            if f == nonlocal_vars["fmts"]
                        ),
                        0,
                    )
                    nonlocal_vars["fmts"] = all_fmts[(idx + 1) % len(all_fmts)]
                    self.config.set("output.subtitle_formats", nonlocal_vars["fmts"])
                elif menu.cursor == 1:
                    nonlocal_vars["max_chars"] = (
                        15
                        if nonlocal_vars["max_chars"] >= 60
                        else nonlocal_vars["max_chars"] + 5
                    )
                    self.config.set("output.max_chars", nonlocal_vars["max_chars"])
                elif menu.cursor == 2:
                    nonlocal_vars["min_chars"] = (
                        4
                        if nonlocal_vars["min_chars"] >= 30
                        else nonlocal_vars["min_chars"] + 2
                    )
                    self.config.set("output.min_chars", nonlocal_vars["min_chars"])
                elif menu.cursor == 3:
                    nonlocal_vars["punctuation"] = not nonlocal_vars["punctuation"]
                    self.config.set(
                        "output.subtitle_punctuation", nonlocal_vars["punctuation"]
                    )
                elif menu.cursor == 4:
                    modes = ["off", "source-first", "target-first"]
                    idx = (
                        modes.index(nonlocal_vars["bilingual"])
                        if nonlocal_vars["bilingual"] in modes
                        else 0
                    )
                    nonlocal_vars["bilingual"] = modes[(idx + 1) % len(modes)]
                    self.config.set("output.bilingual", nonlocal_vars["bilingual"])
                self.config.save()
                items = get_items()
                menu = Menu(
                    title="设置 · 保存设置",
                    items=items,
                    footer="↑↓ 导航  Enter 切换  Esc 返回",
                    theme=self.theme,
                )
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
        menu = Menu(
            title="设置 · 在线服务",
            items=items,
            footer="↑↓ 导航  Enter 修改  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                        sys.stderr.write(
                            f"\033[2K{t.RED}需要安装 questionary：pip install questionary{t.NC}\r\n"
                        )
                        sys.stderr.flush()
                        import time

                        time.sleep(2)
                        raise
                    if menu.cursor == 0:
                        url = questionary.text(
                            "请输入接口地址：", default=nonlocal_vars["base_url"]
                        ).ask()
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
                    sys.stderr.write("\033[H\033[J")
                    sys.stderr.write(f"\033[2K{t.RED}操作取消：{e}{t.NC}\r\n")
                    sys.stderr.flush()
                finally:
                    self.reader.setup_terminal()
                    self._enter_alt_screen()
                items = get_items()
                menu = Menu(
                    title="设置 · 在线服务",
                    items=items,
                    footer="↑↓ 导航  Enter 修改  Esc 返回",
                    theme=self.theme,
                )
                menu.render_full()

    def _view_models_page(self) -> str:
        from .views.models_page import ModelsPage
        from subtap.core.models import ModelRegistry

        page = ModelsPage()
        registry = ModelRegistry(self.config._config)
        statuses = registry.status()
        items = page.build_model_items(statuses)

        menu = Menu(
            title="设置 · 语音模型",
            items=items,
            footer="↑↓ 导航  Enter 操作  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.QUIT:
                return "quit"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                sel = statuses[menu.cursor]
                result = self._model_action_menu(sel, page, registry)
                if result == "quit":
                    return "quit"
                # Re-render after action
                statuses = registry.status()
                items = page.build_model_items(statuses)
                menu = Menu(
                    title="设置 · 语音模型",
                    items=items,
                    footer="↑↓ 导航  Enter 操作  Esc 返回",
                    theme=self.theme,
                )
                menu.render_full()

    def _model_action_menu(self, model_status, page, registry) -> str:
        """Show action menu for a selected model."""
        from subtap.core.models import MODEL_REGISTRY

        t = self.theme
        actions = page.get_actions(model_status.installed)
        menu = Menu(
            title=f"模型：{model_status.name}",
            items=actions,
            footer="↑↓ 导航  Enter 确认  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.ESCAPE:
                return "back"
            elif key == Key.QUIT:
                return "quit"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                selected_action = actions[menu.cursor]
                if selected_action == "返回":
                    return "back"
                elif selected_action == "安装":
                    try:
                        from subtap.core.models import ModelDownloader

                        downloader = ModelDownloader(self.config.to_subtap_config())
                        downloader.download(model_status.name)
                        sys.stderr.write(
                            f"\n{t.GREEN}✓ {model_status.name} 安装完成{t.NC}\n"
                        )
                    except Exception as e:
                        sys.stderr.write(f"\n{t.RED}安装失败：{e}{t.NC}\n")
                    return "back"
                elif selected_action == "删除":
                    sys.stderr.write(
                        f"\n{t.YELLOW}确认删除 {model_status.name}？(Y/N){t.NC} "
                    )
                    confirm = input().strip().upper()
                    if confirm == "Y":
                        try:
                            from subtap.core.models import ModelRemover

                            remover = ModelRemover(self.config.to_subtap_config())
                            remover.remove(model_status.name)
                            sys.stderr.write(
                                f"\n{t.GREEN}✓ {model_status.name} 已删除{t.NC}\n"
                            )
                        except Exception as e:
                            sys.stderr.write(f"\n{t.RED}删除失败：{e}{t.NC}\n")
                    return "back"
                elif selected_action == "查看详情":
                    info: dict[str, object] = MODEL_REGISTRY.get(model_status.name, {})  # type: ignore[assignment]
                    detail_info = {
                        "description": info.get("description", ""),
                        "path": str(model_status.path),
                        "hf_repo": info.get("hf_repo", ""),
                    }
                    detail_lines = page.format_model_detail(
                        model_status.name, detail_info
                    )
                    self._show_detail(detail_lines)
                    # After viewing detail, continue the action menu loop
                    menu.render_full()

    def _show_placeholder(self, message: str) -> None:
        """Show a placeholder message and wait for key."""
        t = self.theme
        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.YELLOW}{message}{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}按任意键返回...{t.NC}\r\n")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

    def _show_detail(self, lines: list[str]) -> None:
        """Show detail info and wait for key."""
        t = self.theme
        sys.stderr.write("\033[H\033[J")
        for line in lines:
            sys.stderr.write(f"\033[2K{line}\r\n")
        sys.stderr.write(f"\r\n\033[2K{t.GRAY}按任意键返回...{t.NC}\r\n")
        sys.stderr.flush()
        self.reader.read_key(timeout=60)

    def _view_wizard(self) -> str:
        wiz = WizardView()

        while True:
            step = wiz.get_state()["step"]

            if step == 0:
                # Step 0: File selection (drag-and-drop input)
                result = self._wizard_step_file(wiz)
            elif step == 1:
                # Step 1: Quality selection (fast/quality menu)
                result = self._wizard_step_quality(wiz)
            elif step == 2:
                # Step 2: Optional glossary selection
                result = self._wizard_step_glossary(wiz)
            elif step == 3:
                # Step 3: Optional manuscript selection
                result = self._wizard_step_manuscript(wiz)
            elif step == 4:
                # Step 4: Output directory selection
                result = self._wizard_step_output(wiz)
            elif step == 5:
                # Step 5: Confirmation
                result = self._wizard_step_confirm(wiz)
            else:
                self._pop_state()
                return "continue"

            if result == "back":
                if step == 0:
                    self._pop_state()
                    return "continue"
                wiz.prev_step()
            elif result == "next":
                wiz.next_step()
            elif result == "quit":
                return "quit"
            elif result == "cancel":
                self._pop_state()
                return "continue"
            elif result == "run":
                return self._execute_wizard_run(wiz)

    def _wizard_step_file(self, wiz: WizardView) -> str:
        t = self.theme
        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.CYAN}[1/6] {WizardView.STEPS[0]}{t.NC}\r\n\r\n")
        sys.stderr.write("\033[2K  拖入音频或视频文件到此处，按 Enter 确认\r\n\r\n")
        sys.stderr.write(
            f"\033[2K{t.GRAY}支持格式：mp3, wav, m4a, mp4, mkv, avi...{t.NC}\r\n\r\n"
        )
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回主菜单  Q 退出{t.NC}\r\n")
        sys.stderr.flush()

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
                    file_path = Path(clean_path).expanduser()
                    if not file_path.is_file():
                        sys.stderr.write(
                            f"\033[8;1H\033[2K{t.RED}文件不存在：{clean_path}{t.NC}\r\n"
                        )
                        sys.stderr.flush()
                        raw_buf = b""
                    elif file_path.suffix.lower() not in AUDIO_VIDEO_EXTENSIONS:
                        sys.stderr.write(
                            f"\033[8;1H\033[2K{t.RED}不支持的格式：{file_path.suffix}{t.NC}\r\n"
                        )
                        sys.stderr.flush()
                        raw_buf = b""
                    else:
                        wiz.select_file(file_path)
                        return "next"
            elif byte == b"\x1b":
                return "cancel"
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

    def _wizard_step_quality(self, wiz: WizardView) -> str:
        items = ["快速模式    速度快，精度一般", "高质量模式  速度慢，精度高"]
        menu = Menu(
            title=f"[2/6] {WizardView.STEPS[1]}",
            items=items,
            footer="↑↓ 导航  Enter 确认  Esc 返回上一步",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                return "back"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                wiz.select_quality("fast" if menu.cursor == 0 else "quality")
                return "next"

    def _wizard_step_glossary(self, wiz: WizardView) -> str:
        glossaries = wiz.list_glossaries()

        items = ["跳过（不使用热词表）"] + [f"  {g.stem}" for g in glossaries]
        menu = Menu(
            title=f"[3/6] {WizardView.STEPS[2]}",
            items=items,
            footer="↑↓ 导航  Enter 确认  Esc 返回上一步",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                return "back"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                if menu.cursor == 0:
                    wiz.select_glossary(None)
                else:
                    wiz.select_glossary(glossaries[menu.cursor - 1])
                return "next"

    def _wizard_step_manuscript(self, wiz: WizardView) -> str:
        manuscripts = wiz.list_manuscripts()

        items = ["跳过（不使用参考文稿）"] + [f"  {m.stem}" for m in manuscripts]
        menu = Menu(
            title=f"[4/6] {WizardView.STEPS[3]}",
            items=items,
            footer="↑↓ 导航  Enter 确认  Esc 返回上一步",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                return "back"
            elif key == Key.UP:
                menu.move_up()
                menu.render_incremental(old_cursor)
            elif key == Key.DOWN:
                menu.move_down()
                menu.render_incremental(old_cursor)
            elif key == Key.ENTER:
                if menu.cursor == 0:
                    wiz.select_manuscript(None)
                else:
                    wiz.select_manuscript(manuscripts[menu.cursor - 1])
                return "next"

    def _wizard_step_output(self, wiz: WizardView) -> str:
        t = self.theme
        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.CYAN}[5/6] {WizardView.STEPS[4]}{t.NC}\r\n\r\n")
        sys.stderr.write("\033[2K  输入输出目录路径，或按 Enter 使用默认目录\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}默认：与源文件相同目录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回上一步  Q 退出{t.NC}\r\n")
        sys.stderr.flush()

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
                    out_dir = Path(clean_path).expanduser()
                    if not out_dir.is_dir():
                        sys.stderr.write(
                            f"\033[8;1H\033[2K{t.RED}目录不存在：{clean_path}{t.NC}\r\n"
                        )
                        sys.stderr.flush()
                        raw_buf = b""
                    else:
                        wiz.select_output_dir(out_dir)
                        return "next"
                else:
                    # Empty input = default directory
                    wiz.select_output_dir(None)
                    return "next"
            elif byte == b"\x1b":
                return "back"
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

    def _wizard_step_confirm(self, wiz: WizardView) -> str:
        t = self.theme
        items = wiz.get_confirm_items()
        menu = Menu(
            title=f"[6/6] {WizardView.STEPS[5]}",
            items=items,
            footer="Enter 开始转录  Esc 返回上一步",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                return "back"
            elif key == Key.ENTER:
                if not wiz.is_complete():
                    sys.stderr.write(
                        f"\033[2K{t.RED}配置不完整，请返回补全必选项{t.NC}\r\n"
                    )
                    sys.stderr.flush()
                    continue
                return "run"

    def _execute_wizard_run(self, wiz: WizardView) -> str:
        cmd = wiz.build_run_command()
        if not cmd:
            self._pop_state()
            return "continue"
        state = wiz.get_state()
        file_name = Path(state["file_path"]).name if state["file_path"] else "未知"
        return self._execute_subprocess(cmd, file_name)

    def _view_new_task(self) -> str:
        t = self.theme
        view = NewTaskView(config=self.config, home_dir=Path.home())

        # 显示拖入提示
        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}新建转录{t.NC}\r\n\r\n")
        sys.stderr.write("\033[2K  拖入音频或视频文件到此处，按 Enter 确认\r\n\r\n")
        sys.stderr.write(
            f"\033[2K{t.GRAY}支持格式：mp3, wav, m4a, mp4, mkv, avi...{t.NC}\r\n\r\n"
        )
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
                        sys.stderr.write(
                            f"\033[8;1H\033[2K{t.RED}文件不存在：{clean_path}{t.NC}\r\n"
                        )
                        sys.stderr.flush()
                        raw_buf = b""
                    elif file_path.suffix.lower() not in AUDIO_VIDEO_EXTENSIONS:
                        sys.stderr.write(
                            f"\033[8;1H\033[2K{t.RED}不支持的格式：{file_path.suffix}{t.NC}\r\n"
                        )
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
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
            if key is None:
                continue
            if key == Key.QUIT:
                return "quit"
            elif key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.ENTER:
                return self._execute_run(view)

    def _run_subprocess_with_progress(
        self,
        cmd: list[str],
        run_env: dict[str, str],
        log_path: Path,
        timeout: float = 3600,
    ) -> tuple[int, str, bool]:
        """启动子进程并渲染实时进度。

        Args:
            timeout: 超时秒数，默认 1 小时

        Returns:
            (returncode, stderr_text, user_quit)
        """
        from .progress_renderer import PipelineProgressRenderer
        import threading

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=run_env,
        )

        # 守护线程持续读取 stderr 防止管道阻塞
        stderr_lines: list[str] = []

        def _drain_stderr():
            try:
                if proc.stderr:
                    for line in proc.stderr:
                        stderr_lines.append(line)
            except (OSError, ValueError):
                pass  # 管道已关闭或进程被 kill，静默退出

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        renderer = PipelineProgressRenderer(stderr=sys.stderr)

        # 渲染线程：轮询 JSONL + 渲染进度
        stop_event = threading.Event()

        def _render_loop():
            try:
                renderer._start_time = time.time()
                renderer._render(renderer._build_lines())
                while not stop_event.is_set():
                    with renderer._lock:
                        events = renderer._read_new_events(log_path)
                        for ev in events:
                            renderer._handle_event(ev)
                        renderer._spinner_index += 1
                        lines = renderer._build_lines()
                        renderer._render(lines)
                    if proc.poll() is not None:
                        break
                    stop_event.wait(0.25)
                # 最终渲染：先等进程结束，再等 drain 线程读完，最后关闭管道
                proc.wait()
                stderr_thread.join(timeout=2)
                if proc.stderr:
                    proc.stderr.close()
                renderer._total_time = time.time() - renderer._start_time
                with renderer._lock:
                    success = proc.returncode == 0
                    result = renderer._build_result_lines(success)
                    renderer._render(result)
            except Exception:
                import traceback

                traceback.print_exc(file=sys.stderr)  # 记录但不阻塞主流程

        render_thread = threading.Thread(target=_render_loop, daemon=True)
        render_thread.start()

        # 主线程键盘轮询：支持 Q 退出 + 超时保护
        start_time = time.time()
        while proc.poll() is None:
            key = self.reader.read_key(timeout=0.2)
            if key == Key.QUIT:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                stop_event.set()
                render_thread.join(timeout=2)
                stderr_thread.join(timeout=2)
                return (-1, "", True)
            if timeout > 0 and (time.time() - start_time) > timeout:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                stop_event.set()
                render_thread.join(timeout=2)
                stderr_thread.join(timeout=2)
                return (-1, "转录超时（超过 {:.0f} 分钟）".format(timeout / 60), False)

        stop_event.set()
        render_thread.join(timeout=5)
        stderr_thread.join(timeout=2)
        return (proc.returncode, "".join(stderr_lines), False)

    def _execute_run(self, view: NewTaskView) -> str:
        cmd = view.build_run_command()
        if not cmd:
            self._pop_state()
            return "continue"
        file_name = view.selected_file.name if view.selected_file else "未知"
        return self._execute_subprocess(cmd, file_name)

    def _execute_subprocess(self, cmd: list[str], file_display_name: str) -> str:
        """Shared subprocess execution with progress rendering."""
        t = self.theme

        import tempfile

        _tmp_dir = Path(tempfile.mkdtemp(prefix="subtap_tui_"))
        log_path = _tmp_dir / "run.log.jsonl"

        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}正在转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}文件：{file_display_name}{t.NC}\r\n\r\n")
        sys.stderr.flush()

        # 预留 10 行给进度渲染
        for _ in range(10):
            sys.stderr.write("\r\n")
        sys.stderr.flush()

        returncode = -1
        stderr_text = ""
        try:
            run_env = _run_env()
            run_env["SUBTAP_EVENT_LOG"] = str(log_path)
            returncode, stderr_text, user_quit = self._run_subprocess_with_progress(
                cmd, run_env, log_path
            )
            if user_quit:
                return "quit"
        except OSError as e:
            sys.stderr.write("\033[H\033[J")
            sys.stderr.write(f"\033[2K{t.RED}✗ 转录程序启动失败：{e}{t.NC}\r\n")
            sys.stderr.write(f"\033[2K\r\n{t.GRAY}Esc 返回{t.NC}\r\n")
            sys.stderr.flush()
            while True:
                key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
                if key in (Key.ESCAPE, Key.ENTER):
                    self._pop_state()
                    return "continue"
                elif key == Key.QUIT:
                    return "quit"
        finally:
            shutil.rmtree(_tmp_dir, ignore_errors=True)

        if returncode != 0:
            err = stderr_text.strip()
            if err:
                lines = err.splitlines()
                key_line = lines[-1] if lines else err[:200]
                sys.stderr.write(f"\033[2K{t.RED}{key_line}{t.NC}\r\n")
                if "No module named" in err:
                    module = err.split("'")[1] if "'" in err else ""
                    if module:
                        sys.stderr.write(
                            f"\033[2K{t.YELLOW}pip install {module}{t.NC}\r\n"
                        )
            sys.stderr.flush()

        sys.stderr.write(f"\033[2K\r\n{t.GRAY}Esc 返回  Q 退出{t.NC}\r\n")
        sys.stderr.flush()

        while True:
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
                key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
                if key in (Key.ESCAPE, Key.QUIT):
                    self._pop_state()
                    return "continue" if key == Key.ESCAPE else "quit"

        menu_items = []
        for r in records:
            status_icon = "✓" if r.is_completed else "✗"
            menu_items.append(
                f"{r.timestamp[:10]}  {r.input_name:<20} {r.duration_str:>8}  {status_icon}"
            )

        menu = Menu(
            title="转录历史",
            items=menu_items,
            footer="↑↓ 导航  Enter 详情  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()

        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
        sys.stderr.write("\033[2K  拖入文件夹到此处，按 Enter 确认\r\n\r\n")
        sys.stderr.write(
            f"\033[2K{t.GRAY}将处理文件夹中所有音频/视频文件{t.NC}\r\n\r\n"
        )
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
                        sys.stderr.write(
                            f"\033[8;1H\033[2K{t.RED}文件夹不存在：{clean_path}{t.NC}\r\n"
                        )
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
        audio_files = sorted(
            [f for f in folder.iterdir() if f.suffix.lower() in AUDIO_VIDEO_EXTENSIONS]
        )

        if not audio_files:
            sys.stderr.write("\033[H\033[J")
            sys.stderr.write(f"\033[2K{t.RED}该文件夹中无音频/视频文件{t.NC}\r\n\r\n")
            sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
            sys.stderr.flush()
            while True:
                key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
                if key in (Key.ESCAPE, Key.QUIT):
                    self._pop_state()
                    return "continue" if key == Key.ESCAPE else "quit"

        sys.stderr.write("\033[H\033[J")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}批量转录{t.NC}\r\n\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}文件夹：{folder}{t.NC}\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}文件数：{len(audio_files)}{t.NC}\r\n\r\n")
        sys.stderr.flush()

        import tempfile

        _tmp_dir = Path(tempfile.mkdtemp(prefix="subtap_batch_"))
        log_path = _tmp_dir / "run.log.jsonl"

        # 从配置读取批量转录参数（与 new_task.py 保持一致的 key）
        fmts = self.config.get("output.subtitle_formats", ["srt"])
        fmt = fmts[0] if fmts else "srt"
        subtitle_lang = self.config.get("output.subtitle_language")
        proofread = self.config.get("llm_proofread", False)
        hotword = self.config.get("llm_hotword", False)

        total = len(audio_files)
        completed = 0
        current_row = 5

        try:
            for i, f in enumerate(audio_files):
                # 标题行：[i/N] 文件名
                sys.stderr.write(
                    f"\033[{current_row};1H\033[2K  {t.GRAY}[{i + 1}/{total}]{t.NC} {f.name}"
                )
                sys.stderr.flush()

                # 准备日志和命令（truncate 而非 unlink，保持 inode 不变）
                log_path.open("w").close()
                cmd = [sys.executable, "-m", "subtap.cli", "run", str(f)]
                # 拼接配置参数
                if fmt:
                    cmd.extend(["--format", fmt])
                if subtitle_lang:
                    cmd.extend(["--subtitle-language", subtitle_lang])
                if proofread or hotword:
                    cmd.extend(["--enhance", "local"])

                returncode = -1
                stderr_text = ""
                try:
                    run_env = _run_env()
                    run_env["SUBTAP_EVENT_LOG"] = str(log_path)
                    returncode, stderr_text, user_quit = (
                        self._run_subprocess_with_progress(cmd, run_env, log_path)
                    )
                    if user_quit:
                        return "quit"
                except OSError:
                    returncode = -1

                # 更新标题行为最终状态
                if returncode == 0:
                    completed += 1
                    sys.stderr.write(
                        f"\033[{current_row};1H\033[2K  {t.GREEN}✓{t.NC} {f.name}"
                    )
                else:
                    err = stderr_text.strip()
                    hint = err.splitlines()[-1][:60] if err else ""
                    sys.stderr.write(
                        f"\033[{current_row};1H\033[2K  {t.RED}✗{t.NC} {f.name} {t.GRAY}{hint}{t.NC}"
                    )
                sys.stderr.flush()

                # 下一个文件：标题(1) + 渲染器占用行(2) + 状态行(1) + 空行(1)
                current_row += 4
        finally:
            shutil.rmtree(_tmp_dir, ignore_errors=True)

        # 完成汇总
        sys.stderr.write(f"\033[{current_row};1H\r\n")
        sys.stderr.write(f"\033[2K{t.GREEN}完成：{completed}/{total}{t.NC}\r\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\r\n")
        sys.stderr.flush()

        while True:
            key = self.reader.read_key(timeout=KEY_READ_TIMEOUT)
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
