"""Tests for observer-process event log reader."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("textual", reason="textual is optional UI dependency")

from subtap.ui.observer import (
    TaskState,
    EventLogCursor,
    _pid_is_alive,
    build_task_presentation,
    summarize_event_log,
)


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


def test_task_presentation_covers_running_completed_and_failed_states(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "pipeline_plan",
                        "timestamp": 10.0,
                        "data": {"stages": ["prepare", "asr", "export"]},
                    }
                ),
                json.dumps(
                    {
                        "event_type": "stage_start",
                        "timestamp": 12.0,
                        "data": {"stage": "asr"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    state = summarize_event_log(log_path)
    output_path = tmp_path / "result.srt"
    output_path.write_text("subtitle", encoding="utf-8")

    running = build_task_presentation(
        state, returncode=None, output_path=output_path, now=42.0
    )
    completed = build_task_presentation(state, returncode=0, output_path=output_path)
    failed = build_task_presentation(state, returncode=2)

    assert running.status == "任务运行中"
    assert running.state is TaskState.RUNNING
    assert running.current_work.startswith("当前任务")
    assert running.current_work.endswith("已用时：00:32")
    assert running.stage_lines == ("· 音频标准化", "▶ 语音识别", "· 字幕导出")
    assert completed.status == "任务已完成"
    assert completed.state is TaskState.COMPLETED
    assert "字幕已生成" in completed.output_text
    assert failed.status == "任务失败（退出码 2）"
    assert failed.state is TaskState.FAILED
    assert "未生成可交付字幕" in failed.output_text


def test_observer_preserves_stage_timing_and_pipeline_terminal_state(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    rows = [
        {
            "schema_version": 2,
            "run_id": "run-1",
            "event_type": "pipeline_plan",
            "timestamp": 10.0,
            "data": {"stages": ["prepare", "asr", "export"]},
        },
        {
            "schema_version": 2,
            "run_id": "run-1",
            "event_type": "stage_start",
            "timestamp": 11.0,
            "data": {"stage": "prepare"},
        },
        {
            "schema_version": 2,
            "run_id": "run-1",
            "event_type": "stage_end",
            "timestamp": 13.5,
            "data": {
                "stage": "prepare",
                "duration_sec": 2.5,
                "status": "success",
            },
        },
        {
            "schema_version": 2,
            "run_id": "run-1",
            "event_type": "model_load",
            "timestamp": 13.7,
            "data": {"stage": "asr", "model": "asr_1.7b-q8"},
        },
        {
            "schema_version": 2,
            "run_id": "run-1",
            "event_type": "pipeline_end",
            "timestamp": 14.0,
            "data": {
                "status": "success",
                "total_duration_sec": 40.0,
                "output_ready": True,
                "subtitle_count": 39,
            },
        },
    ]
    log_path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )

    state = summarize_event_log(log_path)

    assert state["run_id"] == "run-1"
    assert state["pipeline_status"] == "completed"
    assert state["stage_durations"] == {"prepare": 2.5}
    assert state["pipeline_duration_sec"] == 40.0
    presentation = build_task_presentation(state, returncode=None)
    assert presentation.completed_stage_count == 1
    assert presentation.total_stage_count == 3
    assert presentation.elapsed_sec == 40
    assert presentation.subtitle_count == 39
    assert presentation.quality_label == "高质量 · 1.7B"


def test_schema_v2_stage_end_requires_explicit_status(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "run-1",
                "event_type": "stage_end",
                "timestamp": 13.5,
                "data": {"stage": "prepare", "duration_sec": 2.5},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="缺少处理阶段状态"):
        summarize_event_log(log_path)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"status": "success", "output_ready": True}, "总耗时"),
        ({"status": "success", "total_duration_sec": 2.0}, "输出状态"),
    ],
)
def test_schema_v2_pipeline_end_requires_terminal_contract(tmp_path, data, message):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "run-1",
                "event_type": "pipeline_end",
                "timestamp": 13.5,
                "data": data,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        summarize_event_log(log_path)


def test_failed_stage_is_not_rendered_as_completed(tmp_path):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "pipeline_plan",
                        "timestamp": 1.0,
                        "data": {"stages": ["prepare", "asr"]},
                    }
                ),
                json.dumps(
                    {
                        "event_type": "stage_end",
                        "timestamp": 2.0,
                        "data": {"stage": "asr", "status": "failed"},
                    }
                ),
                json.dumps(
                    {
                        "event_type": "pipeline_end",
                        "timestamp": 3.0,
                        "data": {
                            "status": "failed",
                            "total_duration_sec": 2.0,
                            "output_ready": False,
                            "error_message": "模型文件损坏",
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    state = summarize_event_log(log_path)
    presentation = build_task_presentation(state, returncode=1)

    assert "asr" not in state["completed_stages"]
    assert "× 语音识别" in presentation.stage_lines
    assert presentation.failed_stage == "语音识别"
    assert presentation.error_message == "模型文件损坏"


@pytest.mark.parametrize(
    ("terminal", "expected"),
    [
        ("completed", TaskState.COMPLETED),
        ("failed", TaskState.FAILED),
        ("interrupted", TaskState.INTERRUPTED),
    ],
)
def test_historical_task_trusts_persisted_terminal_event(tmp_path, terminal, expected):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "run-1",
                "event_type": "pipeline_end",
                "timestamp": 14.0,
                "data": {
                    "status": "success" if terminal == "completed" else terminal,
                    "output_ready": terminal == "completed",
                    "total_duration_sec": 4.0,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "result.srt"
    if terminal == "completed":
        output.write_text("subtitle", encoding="utf-8")

    presentation = build_task_presentation(
        summarize_event_log(log_path),
        returncode=None,
        output_path=output,
    )

    assert presentation.state is expected


@pytest.mark.parametrize("retryable", [True, False])
def test_failed_task_does_not_offer_unwired_retry(tmp_path, retryable):
    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "run_id": "run-1",
                "event_type": "pipeline_end",
                "timestamp": 14.0,
                "data": {
                    "status": "failed",
                    "output_ready": False,
                    "total_duration_sec": 4.0,
                    "retryable": retryable,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    presentation = build_task_presentation(
        summarize_event_log(log_path),
        returncode=None,
    )

    assert "retry" not in presentation.allowed_actions
    assert "new_task" in presentation.allowed_actions


def test_persisted_log_without_end_event_is_recorded_not_running(tmp_path):
    from subtap.ui.observer import build_task_presentation_from_log

    log_path = tmp_path / "run.log.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "event_type": "stage_start",
                "timestamp": 1.0,
                "data": {"stage": "asr"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    recorded = build_task_presentation_from_log(log_path)
    unverified = build_task_presentation_from_log(
        log_path,
        process=SimpleNamespace(poll=lambda: None),
    )
    dead = build_task_presentation_from_log(
        log_path,
        process=SimpleNamespace(pid=999_999_999, poll=lambda: None),
    )
    running = build_task_presentation_from_log(
        log_path,
        process=SimpleNamespace(pid=os.getpid(), poll=lambda: None),
    )

    assert recorded.state is TaskState.RECORDED
    assert unverified.state is TaskState.OBSERVATION_ERROR
    assert dead.state is TaskState.OBSERVATION_ERROR
    assert running.state is TaskState.RUNNING


def test_observer_reports_only_current_stage_progress(tmp_path):
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
    assert state["progress"] == 50


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

    assert state["progress"] == 50
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
    assert "当前分块：2" in text
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
        assert dashboard.check_action("cancel_task", ()) is True
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
    from textual.widgets import Footer, Header, Static

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
        assert not list(dashboard.query(Header))
        assert len(list(dashboard.query(Footer))) == 1
        assert len(list(dashboard.query("#keys"))) == 0
        assert len(list(dashboard.query("#task-layout"))) == 1
        assert dashboard.check_action("cancel_task", ()) is False
        rendered = str(dashboard.query_one("#status", Static).render())
        assert "任务已完成" in rendered
        assert "result.srt" in rendered
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
    keys = [
        binding.key if hasattr(binding, "key") else binding[0]
        for binding in dashboard.BINDINGS
    ]
    assert "o" not in keys


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


def test_stop_observer_process_group_terminates_detached_task(monkeypatch):
    import signal

    from subtap.cli.pipeline_cli import _stop_observer_process_group

    calls = []
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.os.killpg",
        lambda pgid, signal_number: calls.append((pgid, signal_number)),
    )
    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._process_group_exists",
        lambda _pgid: False,
    )

    _stop_observer_process_group(42)

    assert calls == [(42, signal.SIGTERM)]


def test_observer_process_identity_requires_matching_run_id(monkeypatch):
    from subtap.cli.pipeline_cli import _observer_process_matches_run_id

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout="python -m subtap.cli run clip.wav SUBTAP_RUN_ID=run-other"
        ),
    )

    assert _observer_process_matches_run_id(42, "run-live") is False
    assert _observer_process_matches_run_id(42, "run-other") is True


def _write_jsonl_row(path: Path, task_id: str = "task-1", stage: str = "asr") -> None:
    """Append one valid v2 event row to a JSONL file."""
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
    """Append N valid rows to a JSONL file."""
    stages = ["prepare", "chunk", "asr", "clean", "segment", "align"]
    for i in range(count):
        _write_jsonl_row(path, task_id=task_id, stage=stages[i % len(stages)])


def test_event_log_cursor_cold_load_parses_every_row(tmp_path):
    """10,000 row cold load: parsed_count == 10,000."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 10_000)

    cursor = EventLogCursor(log_path, recent_limit=4)
    cursor.read_initial()
    assert cursor._parsed_count == 10_000


def test_event_log_cursor_unchanged_refreshes_do_no_work(tmp_path):
    """100 unchanged ticks: parsed_count unchanged, no IO."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 100)

    cursor = EventLogCursor(log_path, recent_limit=4)
    cursor.read_initial()
    initial_parsed = cursor._parsed_count

    for _ in range(100):
        cursor.read_updates()

    assert cursor._parsed_count == initial_parsed


def test_event_log_cursor_append_parses_only_additional(tmp_path):
    """Append 3 rows after 100-row cold load: parsed_count += 3."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 100)

    cursor = EventLogCursor(log_path, recent_limit=4)
    cursor.read_initial()
    initial_parsed = cursor._parsed_count

    _write_jsonl_rows(log_path, 3)
    cursor.read_updates()

    assert cursor._parsed_count == initial_parsed + 3


def test_event_log_cursor_partial_row_does_no_parse_work(tmp_path):
    """Partial row + 100 idle ticks: parsed_count unchanged."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 10)

    cursor = EventLogCursor(log_path, recent_limit=4)
    cursor.read_initial()
    initial_parsed = cursor._parsed_count

    with log_path.open("a", encoding="utf-8") as f:
        f.write('{"schema_version": 2, "run_id": "task-1"')

    for _ in range(100):
        cursor.read_updates()
    assert cursor._parsed_count == initial_parsed

    with log_path.open("a", encoding="utf-8") as f:
        f.write(
            ', "event_type": "stage_end", "timestamp": 0,'
            ' "data": {"stage": "asr", "status": "success", "duration_sec": 1.0}}\n'
        )

    cursor.read_updates()
    assert cursor._parsed_count == initial_parsed + 1


def test_event_log_cursor_file_not_found_does_not_raise(tmp_path):
    """Missing file returns state without error and does no work."""
    log_path = tmp_path / "run.log.jsonl"
    cursor = EventLogCursor(log_path, recent_limit=4)

    result = cursor.read_updates()
    assert result is not None
    assert cursor._parsed_count == 0


def test_event_log_cursor_truncation_resets_state_and_counter(tmp_path):
    """File truncation resets cursor state and parsed_count."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 50)

    cursor = EventLogCursor(log_path, recent_limit=4)
    cursor.read_initial()
    assert cursor._parsed_count == 50

    log_path.write_text("", encoding="utf-8")
    _write_jsonl_rows(log_path, 5, task_id="task-2")

    cursor.read_updates()
    assert cursor._parsed_count == 5
    assert cursor.state["run_id"] == "task-2"


def test_event_log_cursor_expected_run_id_matches(tmp_path):
    """Cursor with expected_run_id accepts matching v2 rows."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 5, task_id="task-1")

    cursor = EventLogCursor(log_path, recent_limit=4, expected_run_id="task-1")
    cursor.read_initial()
    assert cursor._parsed_count == 5
    assert cursor.state["run_id"] == "task-1"


def test_event_log_cursor_expected_run_id_mismatch_raises(tmp_path):
    """Cursor with expected_run_id raises ValueError on mismatched v2 row."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 3, task_id="task-1")

    cursor = EventLogCursor(log_path, recent_limit=4, expected_run_id="task-other")
    with pytest.raises(ValueError, match="任务日志行任务标识不匹配"):
        cursor.read_initial()


def test_event_log_cursor_expected_run_id_mid_log_mismatch_raises(tmp_path):
    """Cursor detects run_id mismatch partway through the log."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 3, task_id="task-1")
    _write_jsonl_row(log_path, task_id="task-2")  # different run_id mid-log

    cursor = EventLogCursor(log_path, recent_limit=4, expected_run_id="task-1")
    with pytest.raises(ValueError, match="任务日志行任务标识不匹配"):
        cursor.read_initial()


def test_event_log_cursor_expected_run_id_skips_legacy_v1(tmp_path):
    """Cursor with expected_run_id skips validation for schema v1 rows."""
    log_path = tmp_path / "run.log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        for _ in range(3):
            f.write(
                json.dumps(
                    {
                        "event_type": "stage_start",
                        "timestamp": 1.0,
                        "data": {"stage": "asr"},
                    }
                )
                + "\n"
            )

    cursor = EventLogCursor(log_path, recent_limit=4, expected_run_id="task-1")
    cursor.read_initial()
    assert cursor._parsed_count == 3


def test_event_log_cursor_expected_run_id_none_skips_validation(tmp_path):
    """Cursor with expected_run_id=None accepts any v2 rows."""
    log_path = tmp_path / "run.log.jsonl"
    _write_jsonl_rows(log_path, 5, task_id="task-1")
    _write_jsonl_rows(log_path, 3, task_id="task-2")

    cursor = EventLogCursor(log_path, recent_limit=4)
    cursor.read_initial()
    assert cursor._parsed_count == 8


# ── Positive process-identity TTL cache tests (Phase 8.1) ────────────


@pytest.fixture(autouse=True)
def _clear_identity_cache():
    """Clear the module-level identity cache between tests."""
    yield
    from subtap.ui.observer import _IDENTITY_CACHE

    _IDENTITY_CACHE.clear()


def _fake_clock(clock: list[float]) -> float:
    """Return the current value of *clock* (mutable list for side-effect)."""
    return clock[0]


def _make_alive_spy(monkeypatch, original) -> list[int]:
    """Wrap _pid_is_alive with a call counter. Returns [call_count]."""
    counts = [0]

    def spy(pid):
        counts[0] += 1
        return original(pid)

    monkeypatch.setattr("subtap.ui.observer._pid_is_alive", spy)
    return counts


def _make_ps_spy(monkeypatch, return_value: bool = True) -> list[int]:
    """Mock _observer_process_matches_run_id with call counter."""
    counts = [0]

    def mock_ps(pid, run_id):
        counts[0] += 1
        return return_value

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._observer_process_matches_run_id", mock_ps
    )
    return counts


# ── Test A: first successful verification ──


def test_identity_cache_first_success(monkeypatch):
    """First call with alive PID + matching run-id: ps runs, result True, cache stores entry."""
    from subtap.ui.observer import (
        persisted_process_matches_task,
        _IDENTITY_CACHE,
    )

    pid = os.getpid()
    alive_counts = _make_alive_spy(monkeypatch, _pid_is_alive)
    ps_counts = _make_ps_spy(monkeypatch, return_value=True)

    result = persisted_process_matches_task(pid, "task-a")

    assert result is True
    assert alive_counts[0] == 1, "liveness should be checked exactly once"
    assert ps_counts[0] == 1, "ps should run exactly once"
    assert (pid, "task-a") in _IDENTITY_CACHE
    assert isinstance(_IDENTITY_CACHE[(pid, "task-a")], float)


# ── Test B: repeated calls inside TTL ──


def test_identity_cache_repeated_inside_ttl(monkeypatch):
    """Calls inside TTL: liveness every time, ps skipped on cache hit."""
    from subtap.ui.observer import (
        persisted_process_matches_task,
    )

    pid = os.getpid()
    alive_counts = _make_alive_spy(monkeypatch, _pid_is_alive)
    ps_counts = _make_ps_spy(monkeypatch, return_value=True)

    # First call — establish cache entry
    assert persisted_process_matches_task(pid, "task-a") is True
    assert alive_counts[0] == 1
    assert ps_counts[0] == 1

    # 4 more calls inside TTL
    for _ in range(4):
        assert persisted_process_matches_task(pid, "task-a") is True

    assert alive_counts[0] == 5, "liveness must be checked every call"
    assert ps_counts[0] == 1, "ps must NOT run again inside TTL"


# ── Test C: TTL expiry forces re-verification ──


def test_identity_cache_ttl_expiry(monkeypatch):
    """After TTL expiry: liveness runs, ps runs again, cache timestamp refreshed."""
    from subtap.ui.observer import (
        persisted_process_matches_task,
        _IDENTITY_CACHE,
        _IDENTITY_CACHE_TTL,
    )

    pid = os.getpid()
    clock = [0.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])

    alive_counts = _make_alive_spy(monkeypatch, _pid_is_alive)
    ps_counts = _make_ps_spy(monkeypatch, return_value=True)

    # Establish cache at t=0
    assert persisted_process_matches_task(pid, "task-a") is True
    first_ts = _IDENTITY_CACHE[(pid, "task-a")]
    assert alive_counts[0] == 1
    assert ps_counts[0] == 1

    # Advance beyond TTL
    clock[0] = _IDENTITY_CACHE_TTL + 0.001

    # Should re-verify
    assert persisted_process_matches_task(pid, "task-a") is True
    second_ts = _IDENTITY_CACHE[(pid, "task-a")]
    assert alive_counts[0] == 2
    assert ps_counts[0] == 2, "ps must run again after TTL expiry"
    assert second_ts >= _IDENTITY_CACHE_TTL + 0.001, "cache timestamp must refresh"


# ── Test D: process dies inside TTL — cache evicted immediately ──


def test_identity_cache_process_dies_inside_ttl(monkeypatch):
    """PID death inside TTL: evict cache, return False, do NOT run ps."""
    from subtap.ui.observer import (
        persisted_process_matches_task,
        _IDENTITY_CACHE,
    )

    pid = os.getpid()
    clock = [0.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])

    alive_counts = _make_alive_spy(monkeypatch, _pid_is_alive)
    ps_counts = _make_ps_spy(monkeypatch, return_value=True)

    # Establish cache at t=0
    assert persisted_process_matches_task(pid, "task-a") is True
    assert (pid, "task-a") in _IDENTITY_CACHE
    assert ps_counts[0] == 1

    # Now make _pid_is_alive return False for any PID (use dead pid)
    dead_pid = 999_999_999

    result = persisted_process_matches_task(dead_pid, "task-a")
    assert result is False, "dead PID must return False"
    # alive call count increased by 1 (the call for dead_pid)
    assert alive_counts[0] == 2, "liveness checked for dead PID"
    assert ps_counts[0] == 1, "ps MUST NOT run — dead PID evicts first"
    assert (dead_pid, "task-a") not in _IDENTITY_CACHE, "dead PID entry must be evicted"


# ── Test E: identity mismatch — False not cached ──


def test_identity_cache_mismatch_not_cached(monkeypatch):
    """Identity verifier returning False: result False, no cache entry, re-runs on next call."""
    from subtap.ui.observer import (
        persisted_process_matches_task,
        _IDENTITY_CACHE,
    )

    pid = os.getpid()
    alive_counts = _make_alive_spy(monkeypatch, _pid_is_alive)
    ps_counts = _make_ps_spy(monkeypatch, return_value=False)

    # First call — verifier says False
    result = persisted_process_matches_task(pid, "task-bad")
    assert result is False
    assert alive_counts[0] == 1
    assert ps_counts[0] == 1
    assert (pid, "task-bad") not in _IDENTITY_CACHE, "False must not be cached"

    # Second call — must re-run verifier
    result = persisted_process_matches_task(pid, "task-bad")
    assert result is False
    assert ps_counts[0] == 2, "verifier must run again (False not cached)"


# ── Test F: same PID, different task_id ──


def test_identity_cache_different_task_id_independent(monkeypatch):
    """Same PID with different task_id: cache hit for task-a does not satisfy task-b."""
    from subtap.ui.observer import (
        persisted_process_matches_task,
        _IDENTITY_CACHE,
    )

    pid = os.getpid()
    clock = [0.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])

    alive_counts = _make_alive_spy(monkeypatch, _pid_is_alive)
    ps_counts_a = [0]
    ps_counts_b = [0]

    def mock_ps(pid_arg, run_id):
        if run_id == "task-a":
            ps_counts_a[0] += 1
            return True
        if run_id == "task-b":
            ps_counts_b[0] += 1
            return True
        return False

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._observer_process_matches_run_id", mock_ps
    )

    # task-a succeeds — cached
    assert persisted_process_matches_task(pid, "task-a") is True
    assert ps_counts_a[0] == 1
    assert (pid, "task-a") in _IDENTITY_CACHE

    # task-b — must run independently despite same PID + valid cache for task-a
    assert persisted_process_matches_task(pid, "task-b") is True
    assert ps_counts_b[0] == 1, "task-b must verify independently"
    assert (pid, "task-b") in _IDENTITY_CACHE
    # total ps calls across both keys
    assert ps_counts_a[0] + ps_counts_b[0] == 2

    # task-a cache still valid — no additional ps
    assert persisted_process_matches_task(pid, "task-a") is True
    assert ps_counts_a[0] == 1, "task-a cache hit should not re-run ps"


# ── Test G: bounded cache — never exceeds MAX_ENTRIES ──


def test_identity_cache_bounded(monkeypatch):
    """Creating MAX_ENTRIES + N successful pairs: cache size never exceeds bound."""
    from subtap.ui.observer import (
        persisted_process_matches_task,
        _IDENTITY_CACHE,
        _IDENTITY_CACHE_MAX_ENTRIES,
        _IDENTITY_CACHE_TTL,
    )

    clock = [0.0]
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    alive_counts = _make_alive_spy(monkeypatch, _pid_is_alive)

    ps_counts = [0]

    def mock_ps(pid_arg, run_id):
        ps_counts[0] += 1
        return True

    monkeypatch.setattr(
        "subtap.cli.pipeline_cli._observer_process_matches_run_id", mock_ps
    )

    # Need a real alive PID for each entry.  We reuse os.getpid() but vary
    # the task_id so each (pid, task_id) is a distinct key.
    pid = os.getpid()
    extra = 5
    total = _IDENTITY_CACHE_MAX_ENTRIES + extra

    for i in range(total):
        # Advance clock so each entry lands at a distinct time.  Keep within
        # TTL so entries don't expire during population.
        clock[0] = float(i) * 0.01
        assert (
            persisted_process_matches_task(pid, f"task-{i}") is True
        ), f"task-{i} should verify successfully"

    # Cache must not exceed MAX_ENTRIES
    assert len(_IDENTITY_CACHE) <= _IDENTITY_CACHE_MAX_ENTRIES, (
        f"Cache size {len(_IDENTITY_CACHE)} exceeds bound "
        f"{_IDENTITY_CACHE_MAX_ENTRIES}"
    )

    # With TTL >> 0 and each entry at +0.01s, all within TTL, the
    # earliest entries are pruned when the cache fills up.
    assert (
        ps_counts[0] <= _IDENTITY_CACHE_MAX_ENTRIES + extra
    ), "ps count should match total verification attempts"
