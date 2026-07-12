"""StateStore 测试 — 首次启动追踪、最近任务记录、持久化。"""

from subtap.core.state_store import StateStore


def test_state_store_creates_on_first_read(tmp_path):
    """首次 load 时自动创建 state.json，first_run_time 非空，recent_tasks 为空。"""
    store = StateStore(tmp_path / "state.json")
    state = store.load()
    assert state.first_run_time is not None
    assert state.recent_tasks == []
    assert state.ui_state == {}


def test_state_store_adds_recent_task(tmp_path):
    """添加一条最近任务后，load 返回包含该任务的状态。"""
    store = StateStore(tmp_path / "state.json")
    store.add_recent_task("task-001", "视频.srt", "/output/final.srt")
    state = store.load()
    assert len(state.recent_tasks) == 1
    assert state.recent_tasks[0]["task_id"] == "task-001"
    assert state.recent_tasks[0]["input_name"] == "视频.srt"
    assert state.recent_tasks[0]["output_path"] == "/output/final.srt"


def test_state_store_limits_recent_tasks(tmp_path):
    """添加 25 条后只保留最新 20 条（FIFO）。"""
    store = StateStore(tmp_path / "state.json")
    for i in range(25):
        store.add_recent_task(f"task-{i:03d}", f"file{i}.srt", f"/out/{i}.srt")
    state = store.load()
    assert len(state.recent_tasks) == 20
    # 最新一条应该是 task-024
    assert state.recent_tasks[0]["task_id"] == "task-024"
    # 最旧一条应该是 task-005
    assert state.recent_tasks[-1]["task_id"] == "task-005"


def test_state_store_persists_across_instances(tmp_path):
    """重新创建 StateStore 实例后，数据仍然存在。"""
    path = tmp_path / "state.json"
    store1 = StateStore(path)
    store1.add_recent_task("task-001", "a.srt", "/out/a.srt")

    store2 = StateStore(path)
    state = store2.load()
    assert len(state.recent_tasks) == 1
    assert state.recent_tasks[0]["task_id"] == "task-001"
