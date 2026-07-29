"""StateStore 测试 — 首次启动追踪、最近任务记录、持久化。"""

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier, Event

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
    assert state.recent_tasks[0]["started_at"]


def test_updating_task_status_moves_it_to_most_recent_activity(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.add_recent_task("older", "older.wav", "/out/older.srt", status="running")
    store.add_recent_task("newer", "newer.wav", "/out/newer.srt", status="running")

    store.update_recent_task_status("older", "completed")

    assert [task["task_id"] for task in store.load().recent_tasks[:2]] == [
        "older",
        "newer",
    ]


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


def test_state_store_keeps_observer_reentry_fields(tmp_path):
    store = StateStore(tmp_path / "state.json")

    store.add_recent_task(
        "run-001",
        "访谈.mp3",
        "/output/访谈.srt",
        log_path="/work/run.log.jsonl",
        diagnostic_path="/work/run_latest.log",
        status="running",
    )

    task = store.load().recent_tasks[0]
    assert task["log_path"] == "/work/run.log.jsonl"
    assert task["diagnostic_path"] == "/work/run_latest.log"
    assert task["status"] == "running"


def test_state_store_keeps_task_pid(tmp_path):
    store = StateStore(tmp_path / "state.json")

    store.add_recent_task(
        "run-001",
        "访谈.mp3",
        "/output/访谈.srt",
        status="running",
        pid=4321,
    )

    assert store.load().recent_tasks[0]["pid"] == 4321


def test_state_store_updates_recent_task_status(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.add_recent_task(
        "run-001",
        "访谈.mp3",
        "/output/访谈.srt",
        status="running",
    )

    assert store.update_recent_task_status("run-001", "success") is True
    task = store.load().recent_tasks[0]
    assert task["status"] == "success"
    assert task["completed_at"]
    assert store.update_recent_task_status("missing", "failed") is False


def test_state_store_attaches_pid_without_reverting_a_terminal_status(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.add_recent_task(
        "run-001",
        "访谈.mp3",
        "/output/访谈.srt",
        status="starting",
    )
    assert store.update_recent_task_status("run-001", "success") is True

    assert store.attach_recent_task_process("run-001", 4321) is True

    task = store.load().recent_tasks[0]
    assert task["pid"] == 4321
    assert task["status"] == "success"


def test_state_store_promotes_starting_task_after_process_is_attached(tmp_path):
    store = StateStore(tmp_path / "state.json")
    store.add_recent_task(
        "run-001",
        "访谈.mp3",
        "/output/访谈.srt",
        status="starting",
    )

    assert store.attach_recent_task_process("run-001", 4321) is True

    task = store.load().recent_tasks[0]
    assert task["pid"] == 4321
    assert task["status"] == "running"


def test_state_store_concurrent_adds_keep_every_task(tmp_path):
    path = tmp_path / "state.json"
    StateStore(path).load()
    ready = Barrier(20)

    def add_task(index: int) -> None:
        ready.wait()
        StateStore(path).add_recent_task(
            f"task-{index:02d}",
            f"file-{index:02d}.wav",
            f"/out/{index:02d}.srt",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(add_task, range(20)))

    assert {task["task_id"] for task in StateStore(path).load().recent_tasks} == {
        f"task-{index:02d}" for index in range(20)
    }


def test_state_store_never_exposes_a_partial_write(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "first_run_time": "2026-07-29T00:00:00+00:00",
                "recent_tasks": [{"task_id": "task-01", "status": "running"}],
                "ui_state": {"padding": "x" * 2_000_000},
            }
        ),
        encoding="utf-8",
    )
    store = StateStore(path)
    done = Event()
    ready = Barrier(2)
    invalid_documents: list[str] = []

    def read_state() -> None:
        ready.wait()
        while not done.is_set():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                invalid_documents.append(str(error))

    def update_state() -> None:
        ready.wait()
        for index in range(20):
            assert store.update_recent_task_status("task-01", f"status-{index}")
        done.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        reader = executor.submit(read_state)
        writer = executor.submit(update_state)
        writer.result()
        reader.result()

    assert invalid_documents == []
