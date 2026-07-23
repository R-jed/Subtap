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
    assert state["stage_progress"] == 80
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
    assert state["last_event_at"] == 3.0


def test_observer_reports_monotonic_overall_pipeline_progress(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    rows = [
        {
            "event_type": "pipeline_plan",
            "timestamp": 0.5,
            "data": {
                "stage": "pipeline",
                "stages": [
                    "prepare",
                    "chunk",
                    "asr",
                    "clean",
                    "segment",
                    "align",
                    "hotword",
                    "learn",
                    "export",
                ],
            },
        },
        {
            "event_type": "stage_end",
            "timestamp": 1.0,
            "data": {"stage": "prepare"},
        },
        {
            "event_type": "stage_end",
            "timestamp": 2.0,
            "data": {"stage": "chunk"},
        },
        {
            "event_type": "stage_start",
            "timestamp": 3.0,
            "data": {"stage": "asr"},
        },
        {
            "event_type": "asr_draft_ready",
            "timestamp": 4.0,
            "data": {
                "stage": "asr",
                "progress": 50,
                "item_index": 2,
                "total_items": 4,
            },
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    state = summarize_event_log(log_path)

    assert state["stage_progress"] == 50
    assert state["progress"] == 28


def test_observer_uses_the_pipeline_plan_for_optional_stages(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    rows = [
        {
            "event_type": "pipeline_plan",
            "timestamp": 0.5,
            "data": {
                "stage": "pipeline",
                "stages": [
                    "prepare",
                    "asr",
                    "script_match",
                    "align",
                    "translate",
                    "export",
                ],
            },
        },
        {
            "event_type": "stage_end",
            "timestamp": 1.0,
            "data": {"stage": "prepare"},
        },
        {
            "event_type": "asr_draft_ready",
            "timestamp": 2.0,
            "data": {"stage": "asr", "progress": 50},
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    state = summarize_event_log(log_path)

    assert state["progress"] == 25
    assert state["stage_order"] == rows[0]["data"]["stages"]


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

    class Process:
        returncode = None
        poll_calls = 0

        def poll(self):
            self.poll_calls += 1
            return self.returncode

    process = Process()
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
        process.poll_calls = 0
        dashboard.refresh_from_log()
        await pilot.pause()
        assert len(calls) == 1
        assert process.poll_calls == 1
        await pilot.press("q")


@pytest.mark.asyncio
async def test_observer_dashboard_keeps_completed_task_visible(tmp_path):
    from textual.widgets import Static

    from subtap.ui.observer import _make_observer_dashboard

    output_path = tmp_path / "result.srt"
    output_path.write_text("subtitle", encoding="utf-8")
    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    dashboard = _make_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        output_path=output_path,
    )

    async with dashboard.run_test() as pilot:
        await pilot.pause()
        rendered = str(dashboard.query_one("#status", Static).render())
        footer = str(dashboard.query_one("#keys", Static).render())
        assert "任务已完成" in rendered
        assert "result.srt" in rendered
        assert footer == "F 输出目录   Q 返回"
        assert dashboard.return_value is None
        await pilot.press("q")


@pytest.mark.asyncio
async def test_completed_task_elapsed_time_stops_at_last_event(tmp_path, monkeypatch):
    from textual.widgets import Static

    from subtap.ui.observer import _make_observer_dashboard

    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "stage_start",
                        "timestamp": 10.0,
                        "data": {"stage": "prepare"},
                    }
                ),
                json.dumps(
                    {
                        "event_type": "stage_end",
                        "timestamp": 40.0,
                        "data": {"stage": "export"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("subtap.ui.observer.time.time", lambda: 100.0)
    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    dashboard = _make_observer_dashboard(log_path, process)

    async with dashboard.run_test() as pilot:
        elapsed = str(dashboard.query_one("#current-work", Static).render())
        assert "已用时：00:30" in elapsed
        await pilot.press("q")


@pytest.mark.asyncio
async def test_zero_exit_without_output_is_reported_as_incomplete(tmp_path):
    from textual.widgets import Static

    from subtap.ui.observer import _make_observer_dashboard

    missing_output = tmp_path / "missing.srt"
    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    dashboard = _make_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        output_path=missing_output,
    )

    async with dashboard.run_test() as pilot:
        rendered = str(dashboard.query_one("#status", Static).render())
        result = str(dashboard.query_one("#output", Static).render())
        assert "任务异常" in rendered
        assert "未找到字幕文件" in result
        assert "字幕已生成" not in result
        await pilot.press("q")


@pytest.mark.asyncio
async def test_completed_task_can_open_output_directory(tmp_path, monkeypatch):
    import subprocess

    from subtap.ui.observer import _make_observer_dashboard

    output_path = tmp_path / "output" / "result.srt"
    output_path.parent.mkdir()
    output_path.write_text("subtitle", encoding="utf-8")
    opened = []
    monkeypatch.setattr(
        "subtap.ui.observer.subprocess.run",
        lambda command, **_kwargs: opened.append(command)
        or subprocess.CompletedProcess(command, 0),
    )
    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    dashboard = _make_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        output_path=output_path,
    )

    async with dashboard.run_test() as pilot:
        await pilot.press("f")
        await pilot.press("q")

    assert opened == [["open", str(output_path.parent)]]
    assert all(binding[0] != "o" for binding in dashboard.BINDINGS)


@pytest.mark.asyncio
async def test_failed_task_can_open_diagnostic_log(tmp_path, monkeypatch):
    import subprocess

    from textual.widgets import Static

    from subtap.ui.observer import _make_observer_dashboard

    diagnostic_path = tmp_path / "run_latest.log"
    diagnostic_path.write_text("failure details", encoding="utf-8")
    opened = []
    monkeypatch.setattr(
        "subtap.ui.observer.subprocess.run",
        lambda command, **_kwargs: opened.append(command)
        or subprocess.CompletedProcess(command, 0),
    )
    process = SimpleNamespace(poll=lambda: 2, returncode=2)
    dashboard = _make_observer_dashboard(
        tmp_path / "run.log.jsonl",
        process,
        output_path=tmp_path / "result.srt",
    )

    async with dashboard.run_test() as pilot:
        await pilot.press("d")
        status = str(dashboard.query_one("#action-status", Static).render())
        assert "已打开诊断日志" in status
        await pilot.press("q")

    assert opened == [["open", str(diagnostic_path)]]


@pytest.mark.asyncio
async def test_open_failure_shows_native_error(tmp_path, monkeypatch):
    import subprocess

    from textual.widgets import Static

    from subtap.ui.observer import _make_observer_dashboard

    output_path = tmp_path / "result.srt"
    output_path.write_text("subtitle", encoding="utf-8")
    monkeypatch.setattr(
        "subtap.ui.observer.subprocess.run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 1, "", "LaunchServices 无法打开文件"
        ),
    )
    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    dashboard = _make_observer_dashboard(
        tmp_path / "run.log.jsonl", process, output_path=output_path
    )

    async with dashboard.run_test() as pilot:
        await pilot.press("f")
        status = str(dashboard.query_one("#action-status", Static).render())
        assert "LaunchServices 无法打开文件" in status
        await pilot.press("q")


@pytest.mark.asyncio
async def test_output_shortcuts_explain_when_result_is_unavailable(tmp_path):
    from textual.widgets import Static

    from subtap.ui.observer import _make_observer_dashboard

    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    dashboard = _make_observer_dashboard(tmp_path / "run.log.jsonl", process)

    async with dashboard.run_test() as pilot:
        await pilot.press("f")
        status = str(dashboard.query_one("#action-status", Static).render())
        assert "没有可打开的字幕结果" in status
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
