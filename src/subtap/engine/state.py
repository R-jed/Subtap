"""Stage state machine for pipeline execution."""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class StageStatus(enum.Enum):
    """State of a single pipeline stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


# Chinese labels for status display
STATUS_CN: dict[StageStatus, str] = {
    StageStatus.PENDING: "等待中",
    StageStatus.RUNNING: "执行中",
    StageStatus.SUCCESS: "已完成",
    StageStatus.FAILED: "失败",
    StageStatus.RETRYING: "重试中",
    StageStatus.SKIPPED: "已跳过",
}


@dataclass
class StageState:
    """State of a single pipeline stage with retry tracking."""

    name: str
    name_cn: str
    status: StageStatus = StageStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_msg: str = ""
    result: dict = field(default_factory=dict)
    duration_sec: float = 0.0

    @property
    def can_retry(self) -> bool:
        return self.status == StageStatus.FAILED and self.retry_count < self.max_retries

    @property
    def is_terminal(self) -> bool:
        return self.status in (StageStatus.SUCCESS, StageStatus.SKIPPED)

    def transition(self, new_status: StageStatus) -> None:
        """Transition to a new status."""
        self.status = new_status

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "name_cn": self.name_cn,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "error_msg": self.error_msg,
            "duration_sec": round(self.duration_sec, 2),
        }


# Stage name → Chinese mapping
STAGE_CN: dict[str, str] = {
    "prepare": "音频标准化",
    "chunk": "音频切段",
    "asr": "语音识别",
    "clean": "文本清洗",
    "segment": "智能断句",
    "align": "时间轴对齐",
    "export": "字幕导出",
}

STAGE_ORDER = ["prepare", "chunk", "asr", "clean", "segment", "align", "export"]


class PipelineState:
    """Tracks the state of all stages in a pipeline run."""

    def __init__(self):
        self.stages: dict[str, StageState] = {
            name: StageState(name=name, name_cn=STAGE_CN.get(name, name))
            for name in STAGE_ORDER
        }
        self._listeners: list = []

    def get(self, stage: str) -> StageState:
        return self.stages[stage]

    @property
    def current_stage(self) -> Optional[str]:
        for name in STAGE_ORDER:
            s = self.stages[name]
            if s.status in (StageStatus.RUNNING, StageStatus.RETRYING):
                return name
        return None

    @property
    def progress_pct(self) -> float:
        completed = sum(1 for s in self.stages.values() if s.is_terminal)
        return completed / len(self.stages) * 100

    @property
    def summary(self) -> dict:
        return {name: s.to_dict() for name, s in self.stages.items()}

    def on_change(self, callback) -> None:
        self._listeners.append(callback)

    def _notify(self, stage: str) -> None:
        for cb in self._listeners:
            try:
                cb(stage, self.stages[stage])
            except Exception as e:
                logger.warning("Pipeline state listener callback failed for stage %s: %s", stage, e)

    def mark_running(self, stage: str) -> None:
        s = self.stages[stage]
        s.transition(StageStatus.RUNNING)
        self._notify(stage)

    def mark_success(self, stage: str, result: dict, duration: float) -> None:
        s = self.stages[stage]
        s.result = result
        s.duration_sec = duration
        s.transition(StageStatus.SUCCESS)
        self._notify(stage)

    def mark_failed(self, stage: str, error: str) -> None:
        s = self.stages[stage]
        s.error_msg = error
        s.transition(StageStatus.FAILED)
        self._notify(stage)

    def mark_retrying(self, stage: str) -> None:
        s = self.stages[stage]
        s.retry_count += 1
        s.transition(StageStatus.RETRYING)
        self._notify(stage)

    def mark_skipped(self, stage: str) -> None:
        s = self.stages[stage]
        s.transition(StageStatus.SKIPPED)
        self._notify(stage)

    def reset(self, stage: str) -> None:
        self.stages[stage] = StageState(
            name=stage,
            name_cn=STAGE_CN.get(stage, stage),
        )
        self._notify(stage)
