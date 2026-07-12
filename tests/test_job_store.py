"""JobStore 测试 — 任务目录创建、列出、大小计算、删除。"""

from pathlib import Path

from subtap.core.job_store import JobStore


def test_job_store_creates_job_directory(tmp_path):
    """create 创建对应目录并返回路径。"""
    store = JobStore(tmp_path / "jobs")
    job_dir = store.create("task-001")
    assert job_dir.is_dir()
    assert job_dir == tmp_path / "jobs" / "task-001"


def test_job_store_lists_jobs(tmp_path):
    """list_jobs 返回所有已创建的任务目录。"""
    store = JobStore(tmp_path / "jobs")
    store.create("task-001")
    store.create("task-002")
    jobs = store.list_jobs()
    assert len(jobs) == 2
    names = {p.name for p in jobs}
    assert "task-001" in names
    assert "task-002" in names


def test_job_store_calculates_size(tmp_path):
    """get_size 计算任务目录内所有文件的总字节数。"""
    store = JobStore(tmp_path / "jobs")
    job_dir = store.create("task-001")
    (job_dir / "chunk.wav").write_bytes(b"x" * 1000)
    size = store.get_size("task-001")
    assert size >= 1000


def test_job_store_removes_job(tmp_path):
    """remove 删除任务目录，list_jobs 不再包含该目录。"""
    store = JobStore(tmp_path / "jobs")
    store.create("task-001")
    result = store.remove("task-001")
    assert result is True
    assert len(store.list_jobs()) == 0


def test_job_store_remove_nonexistent(tmp_path):
    """删除不存在的任务返回 False。"""
    store = JobStore(tmp_path / "jobs")
    result = store.remove("no-such-task")
    assert result is False


def test_create_rejects_path_traversal(tmp_path):
    """task_id 包含 .. 时应拒绝。"""
    import pytest

    store = JobStore(tmp_path / "jobs")
    store._root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="invalid task_id"):
        store.create("../../../etc/passwd")


def test_create_rejects_absolute_path(tmp_path):
    """task_id 为绝对路径时应拒绝。"""
    import pytest

    store = JobStore(tmp_path / "jobs")
    store._root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="invalid task_id"):
        store.create("/etc/passwd")


def test_create_rejects_empty_id(tmp_path):
    """空 task_id 应拒绝。"""
    import pytest

    store = JobStore(tmp_path / "jobs")
    store._root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="invalid task_id"):
        store.create("")


def test_remove_rejects_path_traversal(tmp_path):
    """remove 对路径穿越也应拒绝。"""
    import pytest

    store = JobStore(tmp_path / "jobs")
    store._root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="invalid task_id"):
        store.remove("../../../etc")


def test_create_rejects_symlink_outside_jobs_root(tmp_path):
    """任务名不能借符号链接逃逸 jobs 根目录。"""
    import pytest

    root = tmp_path / "jobs"
    outside = tmp_path / "jobs-escape"
    root.mkdir()
    outside.mkdir()
    (root / "task-link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="invalid task_id"):
        JobStore(root).create("task-link")


def test_remove_uses_shared_safe_delete(tmp_path, monkeypatch):
    """任务删除必须经过统一安全删除入口。"""
    store = JobStore(tmp_path / "jobs")
    job_dir = store.create("task-001")
    calls = []

    monkeypatch.setattr(
        "subtap.core.job_store.safe_delete",
        lambda path, *, allowed_roots: calls.append((path, allowed_roots)) or True,
    )

    assert store.remove("task-001") is True
    assert calls == [(job_dir, [store._root])]


def test_job_store_normalizes_relative_root(tmp_path, monkeypatch):
    """相对 jobs 根目录的创建与删除必须使用同一绝对路径。"""
    monkeypatch.chdir(tmp_path)
    store = JobStore(Path("jobs"))

    job_dir = store.create("task-001")

    assert store._root == (tmp_path / "jobs").resolve()
    assert job_dir.is_absolute()
    assert store.remove("task-001") is True
