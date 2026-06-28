"""Phase 23: TUI bridge consumes streaming events."""

from subtap.metrics.events import EventBus, EventType, make_pipeline_event
from subtap.ui.event_bridge import EventBridge


def test_tui_consumes_streaming_events():
    """EventBridge should route streaming events to dashboard consumers."""
    bus = EventBus()

    class MockDashboard:
        def __init__(self):
            self.streaming_events = []

        def update_streaming_event(self, data):
            self.streaming_events.append(data)

    dashboard = MockDashboard()
    bridge = EventBridge(bus, dashboard)
    bridge.connect()

    assert EventType.ASR_DRAFT_READY in bus._subscribers
    assert EventType.ALIGNMENT_READY in bus._subscribers

    event = make_pipeline_event(
        EventType.ALIGNMENT_READY,
        task_id="task-1",
        stage="align",
        subtitle_id=0,
        message_zh="已完成字幕精对齐",
    )
    bridge._on_streaming_event(event)

    assert dashboard.streaming_events[0]["stage"] == "align"
    assert dashboard.streaming_events[0]["subtitle_id"] == 0
