"""Tests for observer-process event log reader."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("textual", reason="textual is optional UI dependency")

from subtap.ui.observer import summarize_event_log


def test_summarize_event_log_restores_latest_status(tmp_path):
    """观察者只读 run.log.jsonl 即可恢复当前阶段、进度和计数。"""
    log_path = tmp_path / "run.log.jsonl"
    rows = [
        {
            "event_type": "stage_start",
            "timestamp": 0.5,
            "data": {"stage": "chunk"},
        },
        {
            "event_type": "audio_chunk_ready",
            "timestamp": 1.0,
            "data": {
                "stage": "chunk",
                "chunk_id": 0,
                "item_index": 1,
                "total_items": 10,
                "progress": 10,
            },
        },
        {
            "event_type": "stage_end",
            "timestamp": 1.5,
            "data": {"stage": "chunk", "duration": 1.0},
        },
        {
            "event_type": "asr_draft_ready",
            "timestamp": 2.0,
            "data": {
                "stage": "asr",
                "chunk_id": 0,
                "model": "asr_0.6b-q8",
                "text": "识别草稿",
            },
        },
        {
            "event_type": "alignment_ready",
            "timestamp": 3.0,
            "data": {
                "stage": "align",
                "subtitle_id": 7,
                "progress": 80,
                "text": "最终字幕",
            },
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    state = summarize_event_log(log_path)

    assert state["stage"] == "align"
    assert state["progress"] == 80
    assert state["chunk_id"] == 0
    assert state["model"] == "asr_0.6b-q8"
    assert state["asr_drafts"] == 1
    assert state["aligned"] == 1
    assert state["completed_stages"] == ["chunk"]
    assert state["item_index"] == 1
    assert state["total_items"] == 10
    assert state["recent_texts"] == ["最终字幕"]
    assert state["started_at"] == 0.5


def test_event_log_ignores_only_incomplete_final_row(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        '{"event_type":"stage_start","data":{"stage":"asr"}}\n{"event_type":',
        encoding="utf-8",
    )

    state = summarize_event_log(log_path)

    assert state["stage"] == "asr"


def test_event_log_ignores_valid_json_without_record_terminator(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        '{"event_type":"stage_start","data":{"stage":"asr"}}',
        encoding="utf-8",
    )

    state = summarize_event_log(log_path)

    assert state["stage"] == "等待中"


def test_event_log_rejects_corrupt_complete_row(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="run.log.jsonl:1"):
        summarize_event_log(log_path)


@pytest.mark.parametrize("row", [[], {"event_type": "stage_start", "data": "asr"}])
def test_event_log_rejects_invalid_row_shape(tmp_path, row):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="run.log.jsonl:1"):
        summarize_event_log(log_path)


def test_observer_dashboard_is_textual_log_reader(tmp_path):
    """观察者 Dashboard 是 Textual App，只读取 run.log.jsonl 状态。"""
    from textual.app import App

    from subtap.ui.observer import _make_observer_dashboard

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
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    dashboard = _make_observer_dashboard(
        log_path=log_path,
        process=SimpleNamespace(poll=lambda: None, returncode=None),
    )

    assert isinstance(dashboard, App)
    text = dashboard.build_status_text()
    assert "当前阶段：asr" in text
    assert "进度：60%" in text
    assert "当前 Chunk：2" in text
    assert "当前模型：asr_0.6b-q8" in text
    assert "隐私：观察者只读取本地日志，不接触音频和模型推理" in text


@pytest.mark.asyncio
async def test_observer_dashboard_supports_detail_and_observe_only_exit(tmp_path):
    from textual.widgets import ProgressBar, RichLog

    from subtap.ui.observer import _make_observer_dashboard

    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "event_type": "asr_draft_ready",
                "timestamp": 1.0,
                "data": {
                    "stage": "asr",
                    "progress": 50,
                    "message_zh": "已生成 ASR 草稿",
                    "text": "这是一条字幕",
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    process = SimpleNamespace(poll=lambda: None, returncode=None)
    dashboard = _make_observer_dashboard(log_path, process)

    async with dashboard.run_test() as pilot:
        assert dashboard.query_one(ProgressBar).progress == 50
        details = dashboard.query_one("#details", RichLog)
        assert details.display is False
        await pilot.press("l")
        assert details.display is True
        await pilot.press("escape")
        assert details.display is False
        await pilot.press("q")

    assert dashboard.return_value == "quit"


@pytest.mark.asyncio
async def test_observer_dashboard_confirms_task_cancellation(tmp_path):
    from subtap.ui.observer import _make_observer_dashboard

    process = SimpleNamespace(poll=lambda: None, returncode=None)
    dashboard = _make_observer_dashboard(tmp_path / "run.log.jsonl", process)

    async with dashboard.run_test() as pilot:
        await pilot.press("x")
        await pilot.press("y")
        await pilot.pause()

    assert dashboard.return_value == "interrupt"


@pytest.mark.asyncio
async def test_observer_does_not_cancel_task_that_finished_during_confirmation(
    tmp_path,
):
    from subtap.ui.observer import _make_observer_dashboard

    class Process:
        returncode = None

        def poll(self):
            return self.returncode

    process = Process()
    dashboard = _make_observer_dashboard(tmp_path / "run.log.jsonl", process)

    async with dashboard.run_test() as pilot:
        await pilot.press("x")
        process.returncode = 0
        await pilot.press("y")
        await pilot.pause()
        assert dashboard.return_value is None
        await pilot.press("q")


@pytest.mark.asyncio
async def test_observer_refresh_parses_log_once(tmp_path, monkeypatch):
    import subtap.ui.observer as observer

    process = SimpleNamespace(poll=lambda: None, returncode=None)
    dashboard = observer._make_observer_dashboard(
        tmp_path / "run.log.jsonl", process, refresh_interval=60
    )

    async with dashboard.run_test() as pilot:
        original = observer.iter_event_log
        calls = []

        def tracked(log_path):
            calls.append(log_path)
            return original(log_path)

        monkeypatch.setattr(observer, "iter_event_log", tracked)
        dashboard.refresh_from_log()
        await pilot.pause()
        assert len(calls) == 1
        await pilot.press("q")


@pytest.mark.asyncio
async def test_observer_dashboard_keeps_completed_task_visible(tmp_path):
    from textual.widgets import Static

    from subtap.ui.observer import _make_observer_dashboard

    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    dashboard = _make_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        output_path=tmp_path / "result.srt",
    )

    async with dashboard.run_test() as pilot:
        await pilot.pause()
        rendered = str(dashboard.query_one("#status", Static).render())
        assert "任务已完成" in rendered
        assert "result.srt" in rendered
        assert dashboard.return_value is None
        await pilot.press("q")


def test_stop_observer_child_terminates_process_group(monkeypatch):
    from subtap.cli.pipeline_cli import _stop_observer_child

    calls = []

    class Process:
        pid = 42

        def poll(self):
            return None

        def wait(self, timeout):
            calls.append(("wait", timeout))
            return 0

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._process_group_exists",
        lambda pgid: False,
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.os.killpg",
        lambda pgid, signal_number: calls.append(("killpg", pgid, signal_number)),
    )

    _stop_observer_child(Process())

    assert calls[0][0:2] == ("killpg", 42)
    assert calls[1] == ("wait", 5)


def test_stop_observer_child_kills_descendants_after_parent_exits(monkeypatch):
    import signal

    from subtap.cli.pipeline_cli import _stop_observer_child

    calls = []
    group_checks = iter([True, False])

    class Process:
        pid = 42

        def poll(self):
            return 0

        def wait(self, timeout):
            calls.append(("wait", timeout))
            return 0

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._process_group_exists",
        lambda pgid: next(group_checks),
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.os.killpg",
        lambda pgid, signal_number: calls.append(("killpg", pgid, signal_number)),
    )

    _stop_observer_child(Process())

    assert calls == [
        ("killpg", 42, signal.SIGTERM),
        ("wait", 5),
        ("killpg", 42, signal.SIGKILL),
    ]


def test_stop_observer_child_accepts_process_group_race(monkeypatch):
    from subtap.cli.pipeline_cli import _stop_observer_child

    class Process:
        pid = 42

        def poll(self):
            return None

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.os.killpg",
        lambda *_args: (_ for _ in ()).throw(ProcessLookupError()),
    )

    _stop_observer_child(Process())
