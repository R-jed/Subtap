"""Pipeline state system with Chinese stage mappings."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional


# Chinese stage name mapping
STAGE_CN: dict[str, str] = {
    "prepare": "音频标准化",
    "chunk": "音频切段",
    "asr": "语音识别",
    "clean": "文本清洗",
    "segment": "智能断句",
    "align": "时间轴对齐",
    "export": "字幕导出",
}

# Stage execution order
STAGE_ORDER = ["prepare", "chunk", "asr", "clean", "segment", "align", "export"]

# Chinese status descriptions
STATUS_CN: dict[str, str] = {
    "idle": "等待中",
    "loading_model": "加载模型中",
    "processing": "处理中",
    "completed": "已完成",
    "failed": "失败",
    "skipped": "已跳过",
}


@dataclass
class PipelineState:
    """Observable pipeline state with Chinese labels."""

    stage: str = ""
    stage_cn: str = ""
    progress: float = 0.0
    status: str = "idle"
    status_cn: str = "等待中"
    current_task: str = ""
    model_used: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    segment_count: int = 0
    elapsed_sec: float = 0.0
    error_msg: str = ""
    suggestion: str = ""
    _listeners: list[Callable[["PipelineState"], None]] = field(default_factory=list, repr=False)

    def update(self, **kwargs) -> None:
        """Update state fields and notify listeners."""
        for k, v in kwargs.items():
            if k == "stage" and isinstance(v, str):
                self.stage = v
                self.stage_cn = STAGE_CN.get(v, v)
            elif k == "status" and isinstance(v, str):
                self.status = v
                self.status_cn = STATUS_CN.get(v, v)
            elif hasattr(self, k):
                setattr(self, k, v)
        self._notify()

    def _notify(self) -> None:
        for listener in self._listeners:
            try:
                listener(self)
            except Exception:
                pass

    def on_change(self, callback: Callable[["PipelineState"], None]) -> None:
        """Register a state change listener."""
        self._listeners.append(callback)

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "stage_cn": self.stage_cn,
            "progress": self.progress,
            "status": self.status,
            "status_cn": self.status_cn,
            "current_task": self.current_task,
            "model_used": self.model_used,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "segment_count": self.segment_count,
            "elapsed_sec": round(self.elapsed_sec, 1),
            "error_msg": self.error_msg,
            "suggestion": self.suggestion,
        }


# Global state instance
_current_state: Optional[PipelineState] = None


def get_state() -> PipelineState:
    """Get or create the global pipeline state."""
    global _current_state
    if _current_state is None:
        _current_state = PipelineState()
    return _current_state


def reset_state() -> PipelineState:
    """Reset the global pipeline state."""
    global _current_state
    _current_state = PipelineState()
    return _current_state
