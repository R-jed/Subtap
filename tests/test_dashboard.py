"""Tests for dashboard system."""

import pytest
from subtap.metrics.events import EventBus, EventType, PipelineEvent
from subtap.ui.event_bridge import EventBridge


def test_dashboard_init():
    """Test PipelineDashboard initialization."""
    from subtap.ui.dashboard import PipelineDashboard
    from subtap.metrics.profiler import PipelineProfiler

    bus = EventBus()
    profiler = PipelineProfiler(bus)
    dashboard = PipelineDashboard(bus, profiler)

    assert dashboard.event_bus == bus
    assert dashboard.profiler == profiler
    assert dashboard._update_throttle == 0.05


def test_dashboard_stage_cn_mapping():
    """Test Chinese stage name mapping."""
    from subtap.ui.dashboard import STAGE_CN

    assert STAGE_CN["asr"] == "语音识别"
    assert STAGE_CN["clean"] == "文本优化"
    assert STAGE_CN["align"] == "字幕对齐"


def test_event_bridge_init():
    """Test EventBridge initialization."""
    bus = EventBus()
    dashboard = None  # Mock dashboard
    bridge = EventBridge(bus, dashboard)
    assert bridge.event_bus == bus
    assert bridge.dashboard == dashboard


def test_event_bridge_connect():
    """Test EventBridge connect."""
    bus = EventBus()
    dashboard = None  # Mock dashboard
    bridge = EventBridge(bus, dashboard)

    bridge.connect()

    assert EventType.STAGE_START in bus._subscribers
    assert EventType.CHUNK_END in bus._subscribers
    assert EventType.PROGRESS in bus._subscribers


def test_event_bridge_on_stage_start():
    """Test EventBridge _on_stage_start callback."""
    bus = EventBus()

    class MockDashboard:
        def __init__(self):
            self.stage = None
        def update_stage(self, stage):
            self.stage = stage

    dashboard = MockDashboard()
    bridge = EventBridge(bus, dashboard)
    bridge.connect()

    # 模拟 STAGE_START 事件
    event = PipelineEvent(
        event_type=EventType.STAGE_START,
        data={"stage": "asr"},
        timestamp=100.0
    )
    bridge._on_stage_start(event)

    assert dashboard.stage == "asr"


def test_event_bridge_on_chunk_end():
    """Test EventBridge _on_chunk_end callback."""
    bus = EventBus()

    class MockDashboard:
        def __init__(self):
            self.chunk_data = None
        def update_chunk(self, data):
            self.chunk_data = data

    dashboard = MockDashboard()
    bridge = EventBridge(bus, dashboard)
    bridge.connect()

    # 模拟 CHUNK_END 事件
    event = PipelineEvent(
        event_type=EventType.CHUNK_END,
        data={"chunk_id": 1, "start_time": 100.0, "end_time": 100.3},
        timestamp=100.3
    )
    bridge._on_chunk_end(event)

    assert dashboard.chunk_data["chunk_id"] == 1


def test_event_bridge_on_progress():
    """Test EventBridge _on_progress callback."""
    bus = EventBus()

    class MockDashboard:
        def __init__(self):
            self.progress = None
        def update_progress(self, data):
            self.progress = data

    dashboard = MockDashboard()
    bridge = EventBridge(bus, dashboard)
    bridge.connect()

    # 模拟 PROGRESS 事件
    event = PipelineEvent(
        event_type=EventType.PROGRESS,
        data={"percent": 50},
        timestamp=100.0
    )
    bridge._on_progress(event)

    assert dashboard.progress["percent"] == 50


def test_cli_run_has_tui_flag():
    """Test CLI run command has --tui flag."""
    from typer.testing import CliRunner
    from subtap.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--tui" in result.output
