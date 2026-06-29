"""Tests for observer-process event log reader."""

from __future__ import annotations

import json

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
