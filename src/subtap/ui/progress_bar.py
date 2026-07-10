"""ANSI 原生进度条组件。

参考 rich Progress 的列式布局，用纯 ANSI escape 序列实现：
  spinner + 阶段文字 + 进度条 + 百分比 + 已用时间

设计原则：
- 不依赖 rich/textual，与现有 TUI 风格一致
- 后台线程尾读 run.log.jsonl，主线程定时渲染
- 就地刷新：用 \\r + \\033[K 覆写当前行
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

# ANSI 颜色（与 theme.py 保持一致）
_CYAN = "\033[1;36m"
_GREEN = "\033[1;32m"
_YELLOW = "\033[1;33m"
_GRAY = "\033[90m"
_NC = "\033[0m"
_BOLD = "\033[1m"

# Braille spinner 帧（与 spinner.py 一致）
_SPINNER_FRAMES = "⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# 进度条字符
_BAR_FILL = "█"
_BAR_EMPTY = "░"

# 阶段中文名映射
_STAGE_CN: dict[str, str] = {
    "prepare": "音频标准化",
    "chunk": "音频切段",
    "asr": "语音识别",
    "clean": "文本清洗",
    "segment": "智能断句",
    "script_match": "文稿匹配",
    "align": "时间轴对齐",
    "translate": "字幕翻译",
    "learn": "热词学习",
    "export": "字幕导出",
}


def _format_elapsed(seconds: float) -> str:
    """格式化已用时间，如 '1:23' 或 '0:45'。"""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class _LogTailReader:
    """后台线程：尾读 run.log.jsonl，解析最新进度状态。"""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "stage": "",
            "stage_cn": "等待中",
            "progress": 0,
            "chunk_id": None,
            "chunks_total": None,
            "model": "",
            "message_zh": "",
            "completed_stages": [],
            "error": None,
        }
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_pos = 0

    def start(self) -> None:
        self._stop.clear()
        self._last_pos = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    @property
    def state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._read_new_lines()
            except Exception:
                pass
            self._stop.wait(0.3)

    def _read_new_lines(self) -> None:
        if not self.log_path.exists():
            return
        try:
            with self.log_path.open("r", encoding="utf-8") as f:
                f.seek(self._last_pos)
                new_data = f.read()
                self._last_pos = f.tell()
        except (OSError, ValueError):
            return

        if not new_data:
            return

        with self._lock:
            for line in new_data.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._apply_event(row)

    def _apply_event(self, row: dict[str, Any]) -> None:
        """根据事件类型更新内部状态。"""
        event_type = row.get("event_type", "")
        data = row.get("data") or {}

        if "stage" in data:
            stage = data["stage"]
            self._state["stage"] = stage
            self._state["stage_cn"] = _STAGE_CN.get(stage, stage)

        if "progress" in data:
            self._state["progress"] = int(data["progress"])

        if "chunk_id" in data:
            self._state["chunk_id"] = data["chunk_id"]

        if "chunks_total" in data:
            self._state["chunks_total"] = data["chunks_total"]

        if "model" in data:
            self._state["model"] = data["model"]

        if "message_zh" in data:
            self._state["message_zh"] = data["message_zh"]

        if event_type == "stage_end":
            stage = data.get("stage", "")
            if stage and stage not in self._state["completed_stages"]:
                self._state["completed_stages"].append(stage)

        if event_type == "error":
            self._state["error"] = data.get("message_zh", data.get("error", "未知错误"))


class ANSIProgressBar:
    """ANSI 原生进度条，用于 TUI 中实时展示子进程转录进度。

    用法：
        bar = ANSIProgressBar(log_path)
        bar.start()
        # ... 子进程运行中 ...
        bar.stop()
        bar.render_final()
    """

    def __init__(self, log_path: Path, bar_width: int = 24):
        self._reader = _LogTailReader(log_path)
        self._bar_width = bar_width
        self._start_time = 0.0
        self._frame_idx = 0
        self._stop = threading.Event()
        self._render_thread: threading.Thread | None = None

    def start(self) -> None:
        """启动进度追踪和渲染。"""
        self._start_time = time.time()
        self._reader.start()
        self._stop.clear()
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()

    def stop(self) -> None:
        """停止进度追踪和渲染。"""
        self._stop.set()
        self._reader.stop()
        if self._render_thread:
            self._render_thread.join(timeout=1.0)

    def _render_loop(self) -> None:
        """后台渲染循环，约 10fps。"""
        while not self._stop.is_set():
            self._render_once()
            self._stop.wait(0.1)

    def _render_once(self) -> None:
        """渲染一帧进度条到 stderr。"""
        state = self._reader.state
        elapsed = time.time() - self._start_time

        # spinner 字符
        spinner = _SPINNER_FRAMES[self._frame_idx % len(_SPINNER_FRAMES)]
        self._frame_idx += 1

        # 进度百分比
        progress = state.get("progress", 0)
        pct = max(0, min(100, progress))

        # 进度条可视化
        filled = int(self._bar_width * pct / 100)
        empty = self._bar_width - filled
        bar = _BAR_FILL * filled + _BAR_EMPTY * empty

        # 阶段文字
        stage_cn = state.get("stage_cn", "处理中")
        message = state.get("message_zh", "")
        detail = f" {message}" if message else ""

        # 模型信息
        model = state.get("model", "")
        model_hint = f" {_GRAY}[{model}]{_NC}" if model else ""

        # 组装行
        line = (
            f"{_CYAN}{spinner}{_NC} "
            f"{_BOLD}{stage_cn}{_NC}{detail}{model_hint} "
            f"{_GREEN}{bar}{_NC} "
            f"{_YELLOW}{pct:>3d}%{_NC} "
            f"{_GRAY}{_format_elapsed(elapsed)}{_NC}"
        )

        # 就地刷新：回车 + 擦行 + 写入
        sys.stderr.write(f"\r\033[2K{line}")
        sys.stderr.flush()

    def render_final(self) -> None:
        """渲染最终状态（成功/失败）。"""
        state = self._reader.state
        elapsed = time.time() - self._start_time

        # 清除进度行
        sys.stderr.write("\r\033[2K")

        if state.get("error"):
            sys.stderr.write(f"{_YELLOW}✗{_NC} 转录失败：{state['error']}\r\n")
        else:
            # 统计完成阶段数
            completed = len(state.get("completed_stages", []))
            sys.stderr.write(
                f"{_GREEN}✓{_NC} 转录完成  "
                f"{_GRAY}{completed} 个阶段 · {_format_elapsed(elapsed)}{_NC}\r\n"
            )
        sys.stderr.flush()

    def render_stages_overview(self) -> None:
        """渲染已完成阶段的概览（可选，在进度条之前调用）。"""
        state = self._reader.state
        completed = state.get("completed_stages", [])
        if not completed:
            return
        for stage in completed:
            cn = _STAGE_CN.get(stage, stage)
            sys.stderr.write(f"  {_GREEN}✓{_NC} {cn}\r\n")
        sys.stderr.flush()
