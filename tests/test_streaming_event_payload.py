"""Phase 23: streaming event payload contract."""

from subtap.metrics.events import EventType, make_pipeline_event


def test_streaming_event_payload_has_required_fields():
    """Streaming events should carry the fields required by TUI/report consumers."""
    event = make_pipeline_event(
        EventType.ASR_DRAFT_READY,
        task_id="task-1",
        stage="asr",
        chunk_id=3,
        segment_id=7,
        progress=50,
        duration_sec=1.25,
        model="asr_0.6b-q8",
        message_zh="已生成 ASR 草稿",
    )

    assert event.event_type == EventType.ASR_DRAFT_READY
    assert event.data["task_id"] == "task-1"
    assert event.data["stage"] == "asr"
    assert event.data["chunk_id"] == 3
    assert event.data["segment_id"] == 7
    assert event.data["timestamp"] > 0
    assert event.data["progress"] == 50
    assert event.data["duration_sec"] == 1.25
    assert event.data["model"] == "asr_0.6b-q8"
    assert event.data["message_zh"] == "已生成 ASR 草稿"
