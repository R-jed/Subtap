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


CSI_MAP = {
    ord("A"): Key.UP, ord("B"): Key.DOWN,
    ord("C"): Key.RIGHT, ord("D"): Key.LEFT,
}
TILDE_MAP = {
    1: Key.ESCAPE, 2: Key.OTHER, 3: Key.DELETE,
    4: Key.OTHER, 5: Key.OTHER, 6: Key.OTHER,
}


class KeyReader:
    """非阻塞键盘读取器，移植自 Mole read_key()。"""

    _atexit_registered = False

    def __init__(self):
        self._fd = sys.stdin.fileno()
        self._original_attrs = None
        self._raw_mode_active = False
        self.force_char_mode = False

    def setup_terminal(self) -> None:
        if not sys.stdin.isatty():
            return
        if self._raw_mode_active:
            return
        import termios
        import tty
        self._original_attrs = termios.tcgetattr(self._fd)
        tty.setraw(self._fd)
        attrs = termios.tcgetattr(self._fd)
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSANOW, attrs)
        self._raw_mode_active = True
        # 注意：atexit 只注册第一个实例的 restore_terminal
        # TuiApp 只创建一个 KeyReader 实例，所以这是安全的
        if not KeyReader._atexit_registered:
            atexit.register(self.restore_terminal)
            KeyReader._atexit_registered = True
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def restore_terminal(self) -> None:
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
        second = self._read_byte(timeout)
        if second is None:
            return Key.ESCAPE
        if second == b"[":
            return self._parse_csi(timeout)
        elif second == b"O":
            return self._parse_ss3(timeout)
        else:
            return Key.ESCAPE

    def _parse_csi(self, timeout: float) -> str:
        buf = b""
        while True:
            byte = self._read_byte(timeout)
            if byte is None:
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
        fb = final[0]
        if fb == ord("~"):
            return TILDE_MAP.get(p1, Key.OTHER)
        return CSI_MAP.get(fb, Key.OTHER)

    def _parse_ss3(self, timeout: float) -> str:
        byte = self._read_byte(timeout)
        if byte is None:
            return Key.OTHER
        SS3_MAP = {
            b"A": Key.UP, b"B": Key.DOWN,
            b"C": Key.RIGHT, b"D": Key.LEFT,
        }
        return SS3_MAP.get(byte, Key.OTHER)

    def _map_normal(self, byte: bytes) -> str:
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
        byte = self._read_byte(timeout)
        if byte is None:
            return None
        if self.force_char_mode:
            return self._map_force_char(byte)
        return self._map_normal(byte)

    def drain_pending_input(self, timeout: float = 0.01, max_drain: int = 100) -> int:
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
