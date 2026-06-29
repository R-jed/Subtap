"""Tests for observer-process event log reader."""

from __future__ import annotations

import json
from types import SimpleNamespace

from subtap.ui.observer import summarize_event_log


def test_summarize_event_log_restores_latest_status(tmp_path):
    """观察者只读 run.log.jsonl 即可恢复当前阶段、进度和计数。"""
    log_path = tmp_path / "run.log.jsonl"
    rows = [
        {
            "event_type": "audio_chunk_ready",
            "timestamp": 1.0,
            "data": {"stage": "chunk", "chunk_id": 0, "progress": 10},
        },
        {
            "event_type": "asr_draft_ready",
            "timestamp": 2.0,
            "data": {"stage": "asr", "chunk_id": 0, "model": "asr_0.6b-q8"},
        },
        {
            "event_type": "alignment_ready",
            "timestamp": 3.0,
            "data": {"stage": "align", "subtitle_id": 7, "progress": 80},
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


def test_observer_dashboard_is_textual_log_reader(tmp_path):
    """观察者 Dashboard 是 Textual App，只读取 run.log.jsonl 状态。"""
    from textual.app import App

    from subtap.ui.observer import ObserverDashboard

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

    dashboard = ObserverDashboard(
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
