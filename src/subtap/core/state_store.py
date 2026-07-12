"""StateStore — 持久化 state.json，管理首次启动时间和最近任务。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class SubtapState(BaseModel):
    """应用持久化状态模型。"""

    first_run_time: str | None = None
    recent_tasks: list[dict] = Field(default_factory=list)
    ui_state: dict = Field(default_factory=dict)


class StateStore:
    """读写 state.json 的持久化存储。"""

    MAX_RECENT_TASKS = 20

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> SubtapState:
        """加载状态，首次访问时自动创建。"""
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return SubtapState.model_validate(data)

        state = SubtapState(
            first_run_time=datetime.now(timezone.utc).isoformat(),
        )
        self._save(state)
        return state

    def add_recent_task(self, task_id: str, input_name: str, output_path: str) -> None:
        """添加一条最近任务记录，超过 MAX_RECENT_TASKS 时移除最旧的。"""
        state = self.load()
        state.recent_tasks.insert(
            0,
            {
                "task_id": task_id,
                "input_name": input_name,
                "output_path": output_path,
            },
        )
        state.recent_tasks = state.recent_tasks[: self.MAX_RECENT_TASKS]
        self._save(state)

    def _save(self, state: SubtapState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
