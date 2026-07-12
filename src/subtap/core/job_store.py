"""JobStore — 管理 jobs/<task-id>/ 任务目录的创建、列出、大小计算和删除。"""

from __future__ import annotations

from pathlib import Path

from subtap.core.safe_delete import safe_delete


class JobStore:
    """任务目录存储管理器。"""

    def __init__(self, jobs_root: Path) -> None:
        self._root = jobs_root.expanduser().resolve()

    def _validate_task_id(self, task_id: str) -> None:
        """验证 task_id 不含路径穿越字符。"""
        if not task_id:
            raise ValueError(f"invalid task_id: {task_id!r}")
        if "/" in task_id or "\\" in task_id or ".." in task_id:
            raise ValueError(f"invalid task_id: {task_id!r}")
        candidate = self._root / task_id
        resolved_root = self._root.resolve()
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(
            resolved_root
        ):
            raise ValueError(f"invalid task_id: {task_id!r}")

    def create(self, task_id: str) -> Path:
        """创建任务目录，返回目录路径。"""
        self._validate_task_id(task_id)
        job_dir = self._root / task_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def list_jobs(self) -> list[Path]:
        """列出所有任务目录（按修改时间降序）。"""
        if not self._root.exists():
            return []
        return sorted(
            [p for p in self._root.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def get_size(self, task_id: str) -> int:
        """计算任务目录内所有文件的总字节数。"""
        self._validate_task_id(task_id)
        job_dir = self._root / task_id
        if not job_dir.exists():
            return 0
        return sum(f.stat().st_size for f in job_dir.rglob("*") if f.is_file())

    def remove(self, task_id: str) -> bool:
        """删除任务目录，返回是否成功。"""
        self._validate_task_id(task_id)
        job_dir = self._root / task_id
        if not job_dir.exists():
            return False
        return safe_delete(job_dir, allowed_roots=[self._root])
