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
        self._thread = threading.Thread(target=self._spin, args=(message,), daemon=True)
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
            self._thread.join(timeout=0.5)
            if self._thread.is_alive():
                # 超时，线程仍在运行（daemon 线程会随主进程退出）
                pass
        sys.stderr.write("\r\033[2K")
        sys.stderr.flush()
