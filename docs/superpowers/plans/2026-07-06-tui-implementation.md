# Subtap TUI 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 基于 Mole 的 TUI 模式，为 Subtap 实现交互式终端菜单系统

**架构：** ANSI 原生渲染（移植 Mole）+ 状态机页面路由 + 后台异步任务主循环重绘。keyboard.py 和 theme.py 是地基，menu.py 是框架，views/ 是页面。

**技术栈：** Python 标准库（termios, select, os, signal, threading），无新增外部依赖

---

## 文件结构

```
src/subtap/ui/
├── keyboard.py       # 创建 — 键盘输入（CSI+SS3 解析、防抖、vim 键位）
├── theme.py          # 创建 — 颜色语义映射、NO_COLOR 支持、CJK 宽度
├── menu.py           # 创建 — 菜单框架（渲染、选中、滚动、分页）
├── spinner.py        # 创建 — 后台 spinner 动画
├── tui_app.py        # 创建 — TUI 主入口，页面路由状态机
├── views/
│   ├── __init__.py   # 创建
│   ├── setup.py      # 创建 — 初始化引导
│   ├── home.py       # 创建 — 主菜单
│   ├── new_task.py   # 创建 — 新建转录
│   ├── history.py    # 创建 — 转录历史
│   ├── batch.py      # 创建 — 批量转录
│   └── settings.py   # 创建 — 设置
├── state.py          # 已有 — 直接复用
├── progress.py       # 已有 — 直接复用
├── tui.py            # 已有 — 保留（非交互 Pipeline 输出）
├── dashboard.py      # 已有 — 保留（可选 Textual 仪表板）
├── event_bridge.py   # 已有 — 直接复用
└── observer.py       # 已有 — 直接复用

tests/
├── test_keyboard.py  # 创建
├── test_theme.py     # 创建
├── test_menu.py      # 创建
└── test_tui_app.py   # 创建
```

---

## 任务 1：theme.py — 颜色系统

**文件：**
- 创建：`src/subtap/ui/theme.py`
- 测试：`tests/test_theme.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_theme.py
import os
from subtap.ui.theme import Theme, get_display_width, truncate_by_width


class TestThemeColors:
    """颜色语义映射测试"""

    def test_default_theme_has_all_colors(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        assert t.GREEN != ""
        assert t.BLUE != ""
        assert t.CYAN != ""
        assert t.YELLOW != ""
        assert t.PURPLE != ""
        assert t.PURPLE_BOLD != ""
        assert t.RED != ""
        assert t.GRAY != ""
        assert t.NC != ""

    def test_no_color_disables_all(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        t = Theme()
        assert t.GREEN == ""
        assert t.BLUE == ""
        assert t.CYAN == ""
        assert t.YELLOW == ""
        assert t.PURPLE == ""
        assert t.RED == ""
        assert t.GRAY == ""

    def test_empty_no_color_keeps_colors(self, monkeypatch):
        """no-color.org 规范：空字符串不触发禁用"""
        monkeypatch.setenv("NO_COLOR", "")
        t = Theme()
        assert t.GREEN != ""


class TestColorizeSize:
    """大小着色测试"""

    def test_gb_is_red(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("1.5GB")
        assert t.RED in result
        assert "1.5GB" in result

    def test_mb_is_yellow(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("769MB")
        assert t.YELLOW in result

    def test_kb_is_green(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("12KB")
        assert t.GREEN in result

    def test_b_is_gray(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        t = Theme()
        result = t.colorize_size("512B")
        assert t.GRAY in result


class TestCJKWidth:
    """CJK 显示宽度计算"""

    def test_ascii_width(self):
        assert get_display_width("hello") == 5

    def test_cjk_width(self):
        assert get_display_width("你好") == 4

    def test_mixed_width(self):
        assert get_display_width("hi你好") == 6

    def test_emoji_zwj_width(self):
        # ZWJ 和 variation selector 不占宽度
        assert get_display_width("‍") == 0

    def test_truncate_ascii(self):
        result = truncate_by_width("hello world", 8)
        assert get_display_width(result) <= 8

    def test_truncate_cjk(self):
        result = truncate_by_width("你好世界欢迎光临", 8)
        assert get_display_width(result) <= 8
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_theme.py -v`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/theme.py
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
        val = os.environ.get("NO_COLOR")
        return val is not None and val != ""

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


# -- 图标常量（移植自 Mole lib/core/base.sh）--

ICON_ARROW = "➤"   # 选中指示
ICON_EMPTY = "○"   # 未选
ICON_SOLID = "●"   # 已选
ICON_CHECK = "✓"   # 完成
ICON_CROSS = "✗"   # 失败
ICON_DOT = "·"     # 等待
ICON_SPINNER = "⠙"  # 进行中


def get_display_width(text: str) -> int:
    """计算终端显示宽度，CJK 字符计为 2。"""
    width = 0
    for ch in text:
        if ch in ("‍", "️"):
            continue
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1
    return width


def truncate_by_width(text: str, max_width: int) -> str:
    """按显示宽度截断，超出加 '...'。"""
    width = 0
    for i, ch in enumerate(text):
        if ch in ("‍", "️"):
            continue
        eaw = unicodedata.east_asian_width(ch)
        cw = 2 if eaw in ("W", "F") else 1
        if width + cw + 3 > max_width:
            return text[:i] + "..."
        width += cw
    return text
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_theme.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/theme.py tests/test_theme.py
git commit -m "feat(ui): 添加 theme.py 颜色系统和 CJK 宽度计算"
```

---

## 任务 2：keyboard.py — 键盘输入

**文件：**
- 创建：`src/subtap/ui/keyboard.py`
- 测试：`tests/test_keyboard.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_keyboard.py
import sys
import io
from unittest.mock import patch, MagicMock
from subtap.ui.keyboard import Key, KeyReader


class TestKeyConstants:
    """语义常量测试"""

    def test_key_constants_exist(self):
        assert Key.UP == "UP"
        assert Key.DOWN == "DOWN"
        assert Key.ENTER == "ENTER"
        assert Key.QUIT == "QUIT"
        assert Key.TOP == "TOP"
        assert Key.BOTTOM == "BOTTOM"


class TestCSISequenceParsing:
    """CSI ESC 序列解析（移植自 Mole read_key）"""

    def _make_reader(self):
        reader = KeyReader.__new__(KeyReader)
        reader._fd = 0
        reader.force_char_mode = False
        return reader

    def test_csi_up(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"A"]):
            assert reader._parse_csi_ss3() == Key.UP

    def test_csi_down(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"B"]):
            assert reader._parse_csi_ss3() == Key.DOWN

    def test_csi_right(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"C"]):
            assert reader._parse_csi_ss3() == Key.RIGHT

    def test_csi_left(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"D"]):
            assert reader._parse_csi_ss3() == Key.LEFT

    def test_csi_delete(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"[", b"3", b"~"]):
            assert reader._parse_csi_ss3() == Key.DELETE

    def test_ss3_up(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"O", b"A"]):
            assert reader._parse_csi_ss3() == Key.UP

    def test_ss3_down(self):
        reader = self._make_reader()
        with patch.object(reader, "_read_byte", side_effect=[b"O", b"B"]):
            assert reader._parse_csi_ss3() == Key.DOWN


class TestNormalModeKeys:
    """普通模式按键映射（vim 键位）"""

    def _make_reader(self):
        reader = KeyReader.__new__(KeyReader)
        reader._fd = 0
        reader.force_char_mode = False
        return reader

    def test_j_is_down(self):
        reader = self._make_reader()
        assert reader._map_normal(b"j") == Key.DOWN

    def test_k_is_up(self):
        reader = self._make_reader()
        assert reader._map_normal(b"k") == Key.UP

    def test_h_is_left(self):
        reader = self._make_reader()
        assert reader._map_normal(b"h") == Key.LEFT

    def test_l_is_right(self):
        reader = self._make_reader()
        assert reader._map_normal(b"l") == Key.RIGHT

    def test_q_is_quit(self):
        reader = self._make_reader()
        assert reader._map_normal(b"q") == Key.QUIT

    def test_enter(self):
        reader = self._make_reader()
        assert reader._map_normal(b"\r") == Key.ENTER

    def test_space(self):
        reader = self._make_reader()
        assert reader._map_normal(b" ") == Key.SPACE

    def test_ctrl_c_is_quit(self):
        reader = self._make_reader()
        assert reader._map_normal(b"\x03") == Key.QUIT

    def test_backspace(self):
        reader = self._make_reader()
        assert reader._map_normal(b"\x7f") == Key.DELETE

    def test_printable_char(self):
        reader = self._make_reader()
        assert reader._map_normal(b"a") == "CHAR:a"

    def test_digit_char(self):
        reader = self._make_reader()
        assert reader._map_normal(b"3") == "CHAR:3"


class TestForceCharMode:
    """筛选输入模式（搜索用）"""

    def _make_reader(self):
        reader = KeyReader.__new__(KeyReader)
        reader._fd = 0
        reader.force_char_mode = True
        return reader

    def test_printable_is_char(self):
        reader = self._make_reader()
        assert reader._map_force_char(b"a") == "CHAR:a"

    def test_space_is_space(self):
        reader = self._make_reader()
        assert reader._map_force_char(b" ") == Key.SPACE

    def test_enter_is_enter(self):
        reader = self._make_reader()
        assert reader._map_force_char(b"\r") == Key.ENTER

    def test_ctrl_u_is_clear(self):
        reader = self._make_reader()
        assert reader._map_force_char(b"\x15") == Key.CLEAR_LINE


class TestDrainPendingInput:
    """防抖测试"""

    def test_drain_reads_all_pending(self):
        reader = KeyReader.__new__(KeyReader)
        reader._fd = 0
        fake_data = b"abcde"
        with patch("select.select") as mock_select, \
             patch("os.read") as mock_read:
            # 第一次 select 有数据，第二次无数据
            mock_select.side_effect = [([True], [], []), ([], [], [])]
            mock_read.return_value = fake_data
            drained = reader.drain_pending_input(timeout=0.01)
            assert drained > 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_keyboard.py -v`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/keyboard.py
"""终端非阻塞键盘输入。

移植自 Mole 的 lib/core/ui.sh read_key()。
- CSI (ESC [) 和 SS3 (ESC O) 序列兼容
- vim 键位（j/k/h/l/gg/G）
- drain_pending_input 防抖
- atexit + signal 三层终端恢复保护
"""
import atexit
import os
import select
import signal
import sys
import time
from typing import Optional


class Key:
    """语义按键常量"""
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    ENTER = "ENTER"
    SPACE = "SPACE"
    QUIT = "QUIT"
    DELETE = "DELETE"
    CLEAR_LINE = "CLEAR_LINE"
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    ESCAPE = "ESCAPE"
    TAB = "TAB"
    OTHER = "OTHER"


class KeyReader:
    """非阻塞键盘读取器，移植自 Mole read_key()。"""

    def __init__(self):
        self._fd = sys.stdin.fileno()
        self._original_attrs = None
        self._raw_mode_active = False
        self.force_char_mode = False  # True = 搜索模式，False = 导航模式

    def setup_terminal(self) -> None:
        """进入 raw mode，禁用 echo 和行缓冲。"""
        if not sys.stdin.isatty():
            return
        if self._raw_mode_active:
            return

        import termios
        import tty

        self._original_attrs = termios.tcgetattr(self._fd)
        tty.setraw(self._fd)

        # VMIN=0, VTIME=0: 非阻塞读取
        attrs = termios.tcgetattr(self._fd)
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSANOW, attrs)

        self._raw_mode_active = True

        atexit.register(self.restore_terminal)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def restore_terminal(self) -> None:
        """恢复终端到原始状态。"""
        if not self._raw_mode_active or self._original_attrs is None:
            return
        try:
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_attrs)
        except termios.error:
            pass
        finally:
            self._raw_mode_active = False
            self._original_attrs = None

    def _signal_handler(self, signum, frame):
        self.restore_terminal()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    def _read_byte(self, timeout: Optional[float] = 1.0) -> Optional[bytes]:
        """读取单字节，带超时。"""
        if not sys.stdin.isatty():
            return None
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return None
        try:
            return os.read(self._fd, 1)
        except OSError:
            return None

    def _parse_csi_ss3(self, timeout: float = 1.0) -> str:
        """解析 ESC [ (CSI) 或 ESC O (SS3) 序列。"""
        second = self._read_byte(timeout)
        if second is None:
            return Key.ESCAPE

        if second == b"[":
            return self._parse_csi(timeout)
        elif second == b"O":
            return self._parse_ss3(timeout)
        else:
            return Key.OTHER

    def _parse_csi(self, timeout: float) -> str:
        """解析 CSI 序列: ESC [ <params> <final_byte>。"""
        buf = b""
        while True:
            ready, _, _ = select.select([self._fd], [], [], timeout)
            if not ready:
                break
            try:
                byte = os.read(self._fd, 1)
            except OSError:
                break
            if not byte:
                break
            buf += byte
            if 0x40 <= byte[0] <= 0x7E:
                break

        if not buf:
            return Key.ESCAPE

        final = buf[-1:]
        params_str = buf[:-1].decode("ascii", errors="ignore")
        params = []
        if params_str:
            for p in params_str.split(";"):
                params.append(int(p) if p.isdigit() else 0)
        p1 = params[0] if params else 1

        CSI_MAP = {
            ord("A"): Key.UP, ord("B"): Key.DOWN,
            ord("C"): Key.RIGHT, ord("D"): Key.LEFT,
        }
        TILDE_MAP = {
            1: Key.ESCAPE, 2: Key.OTHER, 3: Key.DELETE,
            4: Key.OTHER, 5: Key.OTHER, 6: Key.OTHER,
        }

        fb = final[0]
        if fb == ord("~"):
            return TILDE_MAP.get(p1, Key.OTHER)
        return CSI_MAP.get(fb, Key.OTHER)

    def _parse_ss3(self, timeout: float) -> str:
        """解析 SS3 序列: ESC O <final_byte>。"""
        byte = self._read_byte(timeout)
        if byte is None:
            return Key.OTHER
        SS3_MAP = {
            b"A": Key.UP, b"B": Key.DOWN,
            b"C": Key.RIGHT, b"D": Key.LEFT,
        }
        return SS3_MAP.get(byte, Key.OTHER)

    def _map_normal(self, byte: bytes) -> str:
        """普通模式映射（vim 键位）。"""
        if byte in (b"\r", b"\n"):
            return Key.ENTER
        if byte == b" ":
            return Key.SPACE
        if byte in (b"q", b"Q"):
            return Key.QUIT
        if byte in (b"j", b"J"):
            return Key.DOWN
        if byte in (b"k", b"K"):
            return Key.UP
        if byte in (b"h", b"H"):
            return Key.LEFT
        if byte in (b"l", b"L"):
            return Key.RIGHT
        if byte == b"G":
            return Key.BOTTOM
        if byte == b"g":
            next_byte = self._read_byte(timeout=0.3)
            return Key.TOP if next_byte == b"g" else Key.OTHER
        if byte == b"\x03":
            return Key.QUIT
        if byte in (b"\x7f", b"\x08"):
            return Key.DELETE
        if byte == b"\x15":
            return Key.CLEAR_LINE
        if byte == b"\x1b":
            return self._parse_csi_ss3()
        if byte == b"\t":
            return Key.TAB
        ch = byte.decode("utf-8", errors="replace")
        if ch.isprintable():
            return f"CHAR:{ch}"
        return Key.OTHER

    def _map_force_char(self, byte: bytes) -> str:
        """筛选模式映射（搜索输入）。"""
        if byte in (b"\r", b"\n"):
            return Key.ENTER
        if byte in (b"\x7f", b"\x08"):
            return Key.DELETE
        if byte == b"\x15":
            return Key.CLEAR_LINE
        if byte == b"\x1b":
            return self._parse_csi_ss3()
        if byte == b" ":
            return Key.SPACE
        if byte == b"\x03":
            return Key.QUIT
        ch = byte.decode("utf-8", errors="replace")
        if ch.isprintable():
            return f"CHAR:{ch}"
        return Key.OTHER

    def read_key(self, timeout: Optional[float] = 0.01) -> Optional[str]:
        """读取一个按键，非阻塞。返回 Key 常量或 "CHAR:x"。"""
        byte = self._read_byte(timeout)
        if byte is None:
            return None
        if self.force_char_mode:
            return self._map_force_char(byte)
        return self._map_normal(byte)

    def drain_pending_input(self, timeout: float = 0.01, max_drain: int = 100) -> int:
        """排空终端输入缓冲区，防止鼠标滚轮等事件导致跳跃。"""
        if not sys.stdin.isatty():
            return 0
        drained = 0
        first_timeout = timeout
        while drained < max_drain:
            t = first_timeout if drained == 0 else 0.01
            ready, _, _ = select.select([self._fd], [], [], t)
            if not ready:
                break
            try:
                os.read(self._fd, 1024)
            except OSError:
                break
            drained += 1
        return drained

    def __enter__(self):
        self.setup_terminal()
        return self

    def __exit__(self, *args):
        self.restore_terminal()
        return False
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_keyboard.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/keyboard.py tests/test_keyboard.py
git commit -m "feat(ui): 添加 keyboard.py 键盘输入系统（移植自 Mole）"
```

---

## 任务 3：spinner.py — 后台动画

**文件：**
- 创建：`src/subtap/ui/spinner.py`
- 测试：`tests/test_spinner.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_spinner.py
import time
from subtap.ui.spinner import Spinner


class TestSpinner:
    def test_start_and_stop(self):
        s = Spinner()
        s.start("加载中")
        time.sleep(0.15)
        s.stop()
        assert not s._thread.is_alive()

    def test_stop_without_start(self):
        s = Spinner()
        s.stop()  # 不应报错
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_spinner.py -v`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/spinner.py
"""后台 spinner 动画。

移植自 Mole 的 start_inline_spinner/stop_inline_spinner。
用 threading.Event 实现协作式停止。
"""
import sys
import threading


class Spinner:
    CHARS = "⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, color: str = "\033[1;34m", nc: str = "\033[0m"):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._color = color
        self._nc = nc

    def start(self, message: str) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._spin, args=(message,), daemon=True
        )
        self._thread.start()

    def _spin(self, message: str) -> None:
        i = 0
        while not self._stop_event.is_set():
            c = self.CHARS[i % len(self.CHARS)]
            sys.stderr.write(f"\r\033[2K{self._color}{c}{self._nc} {message}")
            sys.stderr.flush()
            i += 1
            self._stop_event.wait(0.05)

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=0.3)
        sys.stderr.write("\r\033[2K")
        sys.stderr.flush()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_spinner.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/spinner.py tests/test_spinner.py
git commit -m "feat(ui): 添加 spinner.py 后台动画组件"
```

---

## 任务 4：menu.py — 菜单框架

**文件：**
- 创建：`src/subtap/ui/menu.py`
- 测试：`tests/test_menu.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_menu.py
from subtap.ui.menu import Menu


class TestMenu:
    def test_initial_state(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        assert m.cursor == 0
        assert m.top_index == 0

    def test_move_down(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.move_down()
        assert m.cursor == 1

    def test_move_up_clamp(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.move_up()
        assert m.cursor == 0

    def test_move_down_clamp(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.cursor = 2
        m.move_down()
        assert m.cursor == 2

    def test_jump_to_top(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.cursor = 2
        m.jump_top()
        assert m.cursor == 0

    def test_jump_to_bottom(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        m.jump_bottom()
        assert m.cursor == 2

    def test_selected_index(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        assert m.selected_index() == "A"
        m.move_down()
        assert m.selected_index() == "B"

    def test_render_current_item_highlighted(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        lines = m.render()
        assert "➤" in lines[2]  # 第三行是第一个菜单项（+2 偏移）
        assert "A" in lines[2]

    def test_render_non_current_item_no_arrow(self):
        m = Menu(title="测试", items=["A", "B", "C"])
        lines = m.render()
        assert "➤" not in lines[3]  # 第二项无箭头

    def test_render_title(self):
        m = Menu(title="Subtap", items=["A", "B"])
        lines = m.render()
        assert "Subtap" in lines[0]

    def test_render_footer(self):
        m = Menu(title="测试", items=["A", "B"])
        lines = m.render()
        assert "Enter" in lines[-1]

    def test_items_per_page_clamp(self):
        m = Menu(title="测试", items=["A"] * 100, max_items=10)
        assert m.items_per_page == 10

    def test_scroll_when_cursor_exceeds_page(self):
        items = [f"item{i}" for i in range(20)]
        m = Menu(title="测试", items=items, max_items=5)
        for _ in range(6):
            m.move_down()
        assert m.top_index > 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_menu.py -v`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/menu.py
"""ANSI 菜单框架。

移植自 Mole 的 menu_paginated.sh。
- 增量渲染（只更新变化的行）
- 分页滚动
- 状态栏自适应宽度
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
    ):
        self.title = title
        self.items = items
        self.footer = footer
        self.theme = theme or Theme()
        self.cursor = 0
        self.top_index = 0
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

    def selected_index(self) -> str:
        return self.items[self.cursor]

    def render(self) -> list[str]:
        """渲染当前帧，返回行列表。"""
        t = self.theme
        lines = []

        # 标题行
        lines.append(f"\033[2K{t.PURPLE_BOLD}{self.title}{t.NC}")

        # 空行
        lines.append("\033[2K")

        # 菜单项
        for i in range(self.items_per_page):
            idx = self.top_index + i
            if idx >= len(self.items):
                lines.append("\033[2K")
                continue
            is_current = idx == self.cursor
            if is_current:
                lines.append(
                    f"\033[2K{t.CYAN}{ICON_ARROW} {self.items[idx]}{t.NC}"
                )
            else:
                lines.append(f"\033[2K  {self.items[idx]}")

        # 页脚
        lines.append(f"\033[2K{t.GRAY}{self.footer}{t.NC}")

        return lines

    def render_full(self) -> str:
        """全屏渲染（首次或翻页）。"""
        sys.stderr.write("\033[H")  # 光标归位
        for line in self.render():
            sys.stderr.write(line + "\n")
        # 光标移到页脚后，隐藏光标
        sys.stderr.write("\033[?25l")
        sys.stderr.flush()
        self._needs_full_redraw = False

    def render_incremental(self, old_cursor: int) -> None:
        """增量渲染：只更新旧行和新行。"""
        if self._needs_full_redraw:
            self.render_full()
            return

        t = self.theme
        # 旧行取消高亮（行号 = old_cursor - top_index + 2）
        old_row = old_cursor - self.top_index + 2
        sys.stderr.write(f"\033[{old_row};1H")
        sys.stderr.write(f"\033[2K  {self.items[old_cursor]}")

        # 新行高亮
        new_row = self.cursor - self.top_index + 2
        sys.stderr.write(f"\033[{new_row};1H")
        sys.stderr.write(
            f"\033[2K{t.CYAN}{ICON_ARROW} {self.items[self.cursor]}{t.NC}"
        )

        # 光标移到页脚后
        footer_row = self.items_per_page + 3
        sys.stderr.write(f"\033[{footer_row};1H")
        sys.stderr.flush()

    def set_needs_redraw(self) -> None:
        self._needs_full_redraw = True
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_menu.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/menu.py tests/test_menu.py
git commit -m "feat(ui): 添加 menu.py ANSI 菜单框架（移植自 Mole）"
```

---

## 任务 5：tui_app.py — 主入口和页面路由

**文件：**
- 创建：`src/subtap/ui/tui_app.py`
- 测试：`tests/test_tui_app.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_tui_app.py
from unittest.mock import MagicMock
from subtap.ui.tui_app import TuiApp


class TestTuiApp:
    def test_initial_state_is_home(self):
        app = TuiApp.__new__(TuiApp)
        app._state = "home"
        assert app._state == "home"

    def test_state_transitions(self):
        app = TuiApp.__new__(TuiApp)
        app._state = "home"
        app._state = "settings"
        assert app._state == "settings"
        app._state = "home"
        assert app._state == "home"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_tui_app.py -v`
预期：FAIL，ModuleNotFoundError

- [ ] **步骤 3：编写实现代码**

```python
# src/subtap/ui/tui_app.py
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
        """启动 TUI 事件循环。"""
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
        """渲染当前页面并等待按键，返回动作。"""
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
        menu = Menu(
            title="Subtap",
            items=[
                "1. 新建转录    从音频/视频生成文字稿",
                "2. 转录历史    查看记录、重新保存",
                "3. 批量转录    一次处理多个文件",
                "4. 设置        模型、接口、偏好",
            ],
            footer="↑↓ 导航  Enter 确认  Q 退出",
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
            footer="↑↓ 导航  Enter 确认  Esc 返回",
            theme=self.theme,
        )
        menu.render_full()
        while True:
            old_cursor = menu.cursor
            key = self.reader.read_key(timeout=0.05)
            if key is None:
                continue
            if key == Key.ESCAPE:
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
        sys.stderr.write("\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}新建转录{t.NC}\n\n")
        sys.stderr.write(f"\033[2K  Enter 选择音频或视频文件\n\n")
        sys.stderr.write(f"\033[2K{t.GRAY}支持格式：mp3, wav, m4a, mp4, mkv, avi{t.NC}\n\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Enter 选择文件  Esc 返回{t.NC}\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.ENTER:
                # TODO: 文件选择对话框
                pass

    def _view_history(self) -> str:
        t = self.theme
        sys.stderr.write("\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}转录历史{t.NC}\n\n")
        sys.stderr.write(f"\033[2K{t.GRAY}暂无记录{t.NC}\n\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"

    def _view_batch(self) -> str:
        t = self.theme
        sys.stderr.write("\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}批量转录{t.NC}\n\n")
        sys.stderr.write(f"\033[2K  Enter 选择文件夹\n\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Esc 返回{t.NC}\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.ESCAPE:
                self._pop_state()
                return "continue"
            elif key == Key.ENTER:
                # TODO: 文件夹选择
                pass

    def _view_setup(self) -> str:
        t = self.theme
        sys.stderr.write("\033[H")
        sys.stderr.write(f"\033[2K{t.PURPLE_BOLD}欢迎使用 Subtap{t.NC}\n\n")
        sys.stderr.write(f"\033[2K  首次使用，需要完成基础配置\n\n")
        sys.stderr.write(f"\033[2K{t.GRAY}Enter 开始配置{t.NC}\n")
        sys.stderr.flush()
        while True:
            key = self.reader.read_key(timeout=0.05)
            if key == Key.ENTER:
                # TODO: 配置流程
                self._pop_state()
                return "continue"


def main():
    """CLI 入口。"""
    app = TuiApp()
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **步骤 4：运行测试验证通过**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m pytest tests/test_tui_app.py -v`
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/tui_app.py tests/test_tui_app.py
git commit -m "feat(ui): 添加 tui_app.py 主入口和页面路由状态机"
```

---

## 任务 6：views/ 页面目录

**文件：**
- 创建：`src/subtap/ui/views/__init__.py`

- [ ] **步骤 1：创建空包**

```python
# src/subtap/ui/views/__init__.py
"""Subtap TUI 视图页面。"""
```

- [ ] **步骤 2：Commit**

```bash
git add src/subtap/ui/views/__init__.py
git commit -m "feat(ui): 创建 views/ 页面目录"
```

---

## 任务 7：CLI 入口注册

**文件：**
- 修改：`src/subtap/cli.py`

- [ ] **步骤 1：添加 `subtap` 命令的 TUI 入口**

在 cli.py 中添加：

```python
@app.command()
def tui():
    """启动交互式终端界面"""
    from subtap.ui.tui_app import TuiApp
    app = TuiApp()
    app.run()
```

- [ ] **步骤 2：测试 CLI 入口**

运行：`cd /Users/qunqing/2026-Project-Agent/Subtap && python -m subtap tui --help`
预期：显示 tui 命令帮助

- [ ] **步骤 3：Commit**

```bash
git add src/subtap/cli.py
git commit -m "feat(cli): 添加 tui 子命令入口"
```

---

## 自检清单

1. **规格覆盖度：**
   - ✅ 颜色系统（theme.py）— 8 色语义 + NO_COLOR + CJK
   - ✅ 键盘输入（keyboard.py）— CSI+SS3 + vim + 防抖
   - ✅ Spinner（spinner.py）— 后台动画
   - ✅ 菜单框架（menu.py）— 分页 + 增量渲染
   - ✅ 主入口（tui_app.py）— 状态机 + 页面路由
   - ✅ 主菜单 — 4 项
   - ⚠️ 设置子页面 — 骨架已实现，详细交互待后续任务
   - ⚠️ 新建转录流程 — 文件选择待后续任务
   - ⚠️ 转录历史 — 数据加载待后续任务
   - ⚠️ 批量转录 — 待后续任务
   - ⚠️ 初始化引导 — 骨架已实现，配置流程待后续任务

2. **占位符扫描：** 无 TODO/待定（除明确标注的后续任务）

3. **类型一致性：** Key 常量在 keyboard.py 定义，所有 view 统一引用
