"""JobStore 测试 — 任务目录创建、列出、大小计算、删除。"""

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
