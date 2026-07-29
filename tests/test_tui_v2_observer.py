"""Signal Desk live observer tests."""

from __future__ import annotations

import json

import pytest
from textual.app import App
from textual.widgets import Footer, ProgressBar, RichLog, Static

from subtap.ui.observer import TaskPresentation, TaskState
from subtap.ui.v2.components import TaskDetails
from subtap.ui.v2.task_views import TaskScreen, TaskView


def _presentation(**overrides: object) -> TaskPresentation:
    values: dict[str, object] = {
        "status": "任务运行中",
        "stage": "asr",
        "progress": 42,
        "model": "small",
        "counts": "ASR 草稿：2  已对齐：1",
        "current_work": "当前分块：3  已用时：00:12",
        "stage_lines": ("✓ 准备", "▶ 语音识别", "· 导出"),
        "recent_texts": ("第一句字幕",),
        "output_text": "[red]未生成可交付字幕[/red]",
        "state": TaskState.RUNNING,
        "elapsed_sec": 12,
        "stage_durations": (("prepare", 1.2),),
    }
    values.update(overrides)
    return TaskPresentation(**values)


class _TaskApp(App[None]):
    def __init__(self, task: TaskPresentation | None = None) -> None:
        super().__init__()
        self._presentation_value = task or _presentation()

    def on_mount(self) -> None:
        self.push_screen(TaskScreen(self._presentation_value))


@pytest.mark.asyncio
async def test_task_screen_refreshes_presentation_without_pushing_a_screen() -> None:
    app = _TaskApp()

    async with app.run_test(size=(90, 56)) as pilot:
        await pilot.pause()
        screen = app.screen
        view = screen.query_one(TaskView)

        await screen.update_presentation(
            _presentation(
                status="任务已完成",
                progress=100,
                output_text="[green]✓ 字幕已生成[/green]\n/tmp/result.srt",
                state=TaskState.COMPLETED,
            )
        )
        await pilot.pause()

        assert app.screen is screen
        assert len(app.screen_stack) == 2
        assert screen.query_one(TaskView) is view
        assert not list(screen.query(ProgressBar))
        visible = "\n".join(str(widget.render()) for widget in screen.query(Static))
        assert "任务已完成" in visible
        assert "/tmp/result.srt" in visible


@pytest.mark.asyncio
async def test_running_refresh_updates_progress_and_preserves_details() -> None:
    app = _TaskApp()

    async with app.run_test(size=(90, 56)) as pilot:
        await pilot.pause()
        screen = app.screen
        details = screen.query_one(TaskDetails)
        details.collapsed = False

        await screen.update_presentation(_presentation(progress=75))
        await pilot.pause()

        assert screen.query_one(ProgressBar).progress == 75
        assert screen.query_one(TaskDetails).collapsed is False


@pytest.mark.asyncio
async def test_running_refresh_preserves_manual_subtitle_scroll() -> None:
    lines = tuple(f"字幕 {index}" for index in range(30))
    app = _TaskApp(_presentation(recent_texts=lines))

    async with app.run_test(size=(60, 24)) as pilot:
        await pilot.pause()
        screen = app.screen
        log = screen.query_one(RichLog)
        log.scroll_to(y=0, animate=False, force=True)
        await pilot.pause()
        assert log.is_vertical_scroll_end is False

        await screen.update_presentation(
            _presentation(recent_texts=lines + ("新字幕",))
        )
        await pilot.pause()

        assert screen.query_one(RichLog).scroll_y == 0


@pytest.mark.asyncio
async def test_live_observer_reduces_event_log_and_refreshes_the_same_screen(
    tmp_path,
) -> None:
    from subtap.ui.v2.observer import _make_v2_observer_dashboard

    class Process:
        returncode = None

        def poll(self):
            return self.returncode

    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "event_type": "asr_draft_ready",
                "timestamp": 1.0,
                "data": {
                    "stage": "asr",
                    "progress": 60,
                    "chunk_id": 2,
                    "model": "asr_0.6b-q8",
                    "text": "实时字幕",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "result.srt"
    process = Process()
    dashboard = _make_v2_observer_dashboard(
        log_path,
        process,
        refresh_interval=60,
        output_path=output_path,
    )

    async with dashboard.run_test(size=(90, 56)) as pilot:
        await pilot.pause()
        screen = dashboard.screen
        view = screen.query_one(TaskView)
        running = "\n".join(str(widget.render()) for widget in screen.query(Static))
        assert "任务运行中" in running
        assert "asr_0.6b-q8" in running
        assert screen.query_one("#task-live-summary").region.height == 3

        output_path.write_text("subtitle", encoding="utf-8")
        process.returncode = 0
        await dashboard.refresh_from_log()
        await pilot.pause()

        assert dashboard.screen is screen
        assert len(dashboard.screen_stack) == 1
        assert screen.query_one(TaskView) is view
        completed = "\n".join(str(widget.render()) for widget in screen.query(Static))
        assert "任务已完成" in completed
        assert str(output_path) in completed


def test_v2_observer_keeps_twelve_recent_subtitles(tmp_path) -> None:
    from subtap.ui.v2.observer import _make_v2_observer_dashboard

    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        "".join(
            json.dumps(
                {
                    "event_type": "alignment_ready",
                    "timestamp": float(index),
                    "data": {"stage": "align", "text": f"字幕 {index}"},
                },
                ensure_ascii=False,
            )
            + "\n"
            for index in range(15)
        ),
        encoding="utf-8",
    )
    process = type("Process", (), {"poll": lambda self: None})()

    presentation = _make_v2_observer_dashboard(
        log_path, process, refresh_interval=60
    )._build_presentation()

    assert presentation.recent_texts == tuple(f"字幕 {index}" for index in range(3, 15))


def test_v2_observer_turns_invalid_schema_into_observation_error(tmp_path) -> None:
    from subtap.ui.v2.observer import _make_v2_observer_dashboard

    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "event_type": "stage_start",
                "data": {"stage": "asr"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    process = type("Process", (), {"poll": lambda self: None})()

    presentation = _make_v2_observer_dashboard(
        log_path, process, refresh_interval=60
    )._build_presentation()

    assert presentation.state is TaskState.OBSERVATION_ERROR
    assert "不支持的任务日志版本" in presentation.status


@pytest.mark.asyncio
async def test_v2_observer_confirms_interrupt_and_keeps_interrupted_view(
    tmp_path, monkeypatch
) -> None:
    import subtap.ui.v2.observer as observer

    class Process:
        returncode = None

        def poll(self):
            return self.returncode

    process = Process()
    stopped = []

    def stop_child(selected_process) -> None:
        stopped.append(selected_process)
        selected_process.returncode = -15

    monkeypatch.setattr(observer, "_stop_observer_child", stop_child)
    dashboard = observer._make_v2_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        refresh_interval=60,
        run_id="task-1",
    )

    async with dashboard.run_test(size=(90, 56)) as pilot:
        task_screen = dashboard.screen
        await pilot.press("x")
        assert stopped == []
        assert isinstance(dashboard.screen, observer.InterruptTaskScreen)

        await dashboard.refresh_from_log()
        assert isinstance(dashboard.screen, observer.InterruptTaskScreen)

        await pilot.press("y")
        await pilot.pause()

        assert stopped == [process]
        assert dashboard.screen is task_screen
        assert dashboard.is_running is True
        visible = "\n".join(
            str(widget.render()) for widget in task_screen.query(Static)
        )
        assert "已中断" in visible
        assert "任务未完成" in visible
        persisted = json.loads(
            (tmp_path / "run.log.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        )
        assert persisted["event_type"] == "pipeline_end"
        assert persisted["data"]["status"] == "interrupted"
        assert persisted["run_id"] == "task-1"
        assert persisted["data"]["total_duration_sec"] >= 0

        await pilot.press("q")
        await pilot.pause()

    assert dashboard.return_value == "interrupt"


@pytest.mark.asyncio
async def test_q_detaches_without_interrupting_running_child(
    tmp_path, monkeypatch
) -> None:
    import subtap.ui.v2.observer as observer

    process = type(
        "Process",
        (),
        {"returncode": None, "poll": lambda self: self.returncode},
    )()
    stopped = []
    monkeypatch.setattr(
        observer,
        "_stop_observer_child",
        lambda selected_process: stopped.append(selected_process),
    )
    dashboard = observer._make_v2_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        refresh_interval=60,
    )

    async with dashboard.run_test() as pilot:
        assert dashboard.screen.check_action("open_output_file", ()) is False
        assert dashboard.screen.check_action("open_output_directory", ()) is False
        assert dashboard.screen.check_action("open_diagnostics", ()) is False
        await pilot.press("q")
        await pilot.pause()

    assert dashboard.return_value == "quit"
    assert stopped == []
    assert process.poll() is None


@pytest.mark.asyncio
async def test_v2_observer_preserves_output_diagnostic_and_overview_actions(
    tmp_path, monkeypatch
) -> None:
    import subtap.ui.v2.observer as observer

    output_path = tmp_path / "output" / "result.srt"
    output_path.parent.mkdir()
    output_path.write_text("subtitle", encoding="utf-8")
    diagnostic_path = tmp_path / "run_latest.log"
    diagnostic_path.write_text("details", encoding="utf-8")
    process = type(
        "Process",
        (),
        {"returncode": 0, "poll": lambda self: self.returncode},
    )()
    opened = []
    monkeypatch.setattr(
        observer,
        "_open_file_cross_platform",
        lambda path: opened.append(path),
    )
    dashboard = observer._make_v2_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        refresh_interval=60,
        output_path=output_path,
        diagnostic_path=diagnostic_path,
    )

    async with dashboard.run_test() as pilot:
        details = dashboard.screen.query_one(TaskDetails)
        details.collapsed = False
        await pilot.press("escape")
        assert details.collapsed is True

        await pilot.press("f")
        await pilot.press("o")
        await pilot.press("d")
        assert opened == [output_path.parent, output_path, diagnostic_path]
        assert len(list(dashboard.query(Footer))) == 1
        assert dashboard.screen.check_action("interrupt_task", ()) is False

        await pilot.press("q")
        await pilot.pause()

    assert dashboard.return_value == "quit"


async def test_observer_lifecycle_a_complete_b_starts_fresh(
    tmp_path, monkeypatch
) -> None:
    """A completes → B starts: one timer, new cursor, B RUNNING."""
    from subtap.ui.v2.observer import ObserverHostApp, ObserverTaskScreen

    class FakeProcess:
        returncode = None

        def poll(self):
            return self.returncode

    log_a = tmp_path / "run_a.log.jsonl"
    log_b = tmp_path / "run_b.log.jsonl"

    _write_jsonl_rows(log_a, 10, task_id="task-a")
    _write_jsonl_rows(log_b, 5, task_id="task-b")

    process_a = FakeProcess()
    process_b = FakeProcess()

    class _TestApp(ObserverHostApp):
        pass

    app = _TestApp()
    app._log_path = log_a
    app._process = process_a
    app._output_path = tmp_path / "out.srt"
    app._run_id = "task-a"
    app._diagnostic_path = tmp_path / "diag.log"
    app._interrupted = False
    app._event_cursor = None
    app._observer_timer = None
    app.theme = "textual-dark"

    async with app.run_test(size=(90, 56)) as pilot:
        await pilot.pause()

        app._task_screen = ObserverTaskScreen(app._build_presentation())
        app.push_screen(app._task_screen)
        app._start_observer_timer()
        await pilot.pause()
        assert app._task_screen.presentation.state is TaskState.RUNNING

        (tmp_path / "out.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n字幕\n", encoding="utf-8"
        )
        process_a.returncode = 0
        with log_a.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "schema_version": 2,
                        "run_id": "task-a",
                        "event_type": "pipeline_end",
                        "timestamp": 100.0,
                        "data": {
                            "stage": "export",
                            "status": "success",
                            "total_duration_sec": 10.0,
                            "output_ready": True,
                        },
                    }
                )
                + "\n"
            )
        await app.refresh_from_log()
        await pilot.pause()
        assert app._task_screen.presentation.state is TaskState.COMPLETED
        assert app._observer_timer is None

        app._log_path = log_b
        app._process = process_b
        app._run_id = "task-b"
        app._interrupted = False
        app._event_cursor = None
        app._observer_timer = None
        app._task_screen = ObserverTaskScreen(app._build_presentation())
        app.push_screen(app._task_screen)
        app._start_observer_timer()
        await pilot.pause()
        assert app._task_screen.presentation.state is TaskState.RUNNING
        assert app._observer_timer is not None


def _write_jsonl_row(path: Path, task_id: str = "task-1", stage: str = "asr") -> None:
    from subtap.metrics.events import EventType, make_pipeline_event

    event = make_pipeline_event(
        EventType.STAGE_START,
        task_id=task_id,
        stage=stage,
    )
    payload = {
        "schema_version": 2,
        "run_id": task_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp,
        "data": event.data,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_jsonl_rows(path: Path, count: int, task_id: str = "task-1") -> None:
    stages = ["prepare", "chunk", "asr", "clean", "segment", "align"]
    for i in range(count):
        _write_jsonl_row(path, task_id=task_id, stage=stages[i % len(stages)])
