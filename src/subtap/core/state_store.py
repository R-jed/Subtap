"""StateStore — 持久化 state.json，管理首次启动时间和最近任务。"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

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
        self._lock_path = path.with_name(f".{path.name}.lock")

    def load(self) -> SubtapState:
        """加载状态，首次访问时自动创建。"""
        with self._locked():
            return self._load()

    def _load(self) -> SubtapState:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return SubtapState.model_validate(data)

        state = SubtapState(
            first_run_time=datetime.now(timezone.utc).isoformat(),
        )
        self._save(state)
        return state

    def add_recent_task(
        self,
        task_id: str,
        input_name: str,
        output_path: str,
        *,
        log_path: str | None = None,
        diagnostic_path: str | None = None,
        status: str | None = None,
        pid: int | None = None,
    ) -> None:
        """添加一条最近任务记录，超过 MAX_RECENT_TASKS 时移除最旧的。"""
        with self._locked():
            state = self._load()
            record: dict[str, str | int] = {
                "task_id": task_id,
                "input_name": input_name,
                "output_path": output_path,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            if log_path is not None:
                record["log_path"] = log_path
            if diagnostic_path is not None:
                record["diagnostic_path"] = diagnostic_path
            if status is not None:
                record["status"] = status
            if pid is not None:
                record["pid"] = pid
            state.recent_tasks = [
                task for task in state.recent_tasks if task.get("task_id") != task_id
            ]
            state.recent_tasks.insert(0, record)
            state.recent_tasks = state.recent_tasks[: self.MAX_RECENT_TASKS]
            self._save(state)

    def update_recent_task_status(self, task_id: str, status: str) -> bool:
        """更新最近任务状态；任务不存在时保持状态文件不变。"""
        with self._locked():
            state = self._load()
            for index, task in enumerate(state.recent_tasks):
                if task.get("task_id") == task_id:
                    task["status"] = status
                    if status in {
                        "success",
                        "completed",
                        "failed",
                        "interrupted",
                        "partial_failure",
                    }:
                        task["completed_at"] = datetime.now(timezone.utc).isoformat()
                    state.recent_tasks.insert(0, state.recent_tasks.pop(index))
                    self._save(state)
                    return True
            return False

    def attach_recent_task_process(self, task_id: str, pid: int) -> bool:
        """记录子进程；仅将仍在启动中的任务推进到运行态。"""
        with self._locked():
            state = self._load()
            for task in state.recent_tasks:
                if task.get("task_id") == task_id:
                    task["pid"] = pid
                    if task.get("status") == "starting":
                        task["status"] = "running"
                    self._save(state)
                    return True
            return False

    def remove_recent_task(self, task_id: str) -> bool:
        """移除一条未能启动的任务记录。"""
        with self._locked():
            state = self._load()
            remaining = [
                task for task in state.recent_tasks if task.get("task_id") != task_id
            ]
            if len(remaining) == len(state.recent_tasks):
                return False
            state.recent_tasks = remaining
            self._save(state)
            return True

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _save(self, state: SubtapState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(state.model_dump_json(indent=2))
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self._path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
