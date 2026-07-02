"""Tests for dashboard system."""

import inspect

import pytest

pytest.importorskip("textual", reason="textual is optional UI dependency")

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


@pytest.mark.asyncio
async def test_dashboard_runs_startup_callback_on_mount(monkeypatch):
    """Textual mount 后再启动 pipeline，避免和 App 初始化抢事件循环。"""
    from subtap.metrics.profiler import PipelineProfiler
    from subtap.ui.dashboard import PipelineDashboard

    bus = EventBus()
    dashboard = PipelineDashboard(bus, PipelineProfiler(bus))
    called = []

    def fake_run_worker(work, *args, **kwargs):
        if inspect.iscoroutine(work):
            work.close()

    dashboard.set_startup_callback(lambda: called.append(True))
    monkeypatch.setattr(dashboard, "run_worker", fake_run_worker)

    await dashboard.on_mount()

    assert called == [True]


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
        event_type=EventType.STAGE_START, data={"stage": "asr"}, timestamp=100.0
    )
    bridge._on_stage_start(event)

    assert dashboard.stage == "asr"


def test_event_bridge_on_chunk_end():
    """Test EventBridge _on_chunk_end callback."""
    bus = EventBus()

    class MockDashboard:
        def __init__(self):
            self.chunk_data = None

        def update_chunk(self, current, total):
            self.chunk_data = (current, total)

    dashboard = MockDashboard()
    bridge = EventBridge(bus, dashboard)
    bridge.connect()

    # 模拟 CHUNK_END 事件
    event = PipelineEvent(
        event_type=EventType.CHUNK_END,
        data={"chunk_id": 1, "start_time": 100.0, "end_time": 100.3},
        timestamp=100.3,
    )
    bridge._on_chunk_end(event)

    assert dashboard.chunk_data == (1, 1)


def test_event_bridge_on_progress():
    """Test EventBridge _on_progress callback."""
    bus = EventBus()

    class MockDashboard:
        def __init__(self):
            self.progress = None

        def update_progress(self, progress):
            self.progress = progress

    dashboard = MockDashboard()
    bridge = EventBridge(bus, dashboard)
    bridge.connect()

    # 模拟 PROGRESS 事件
    event = PipelineEvent(
        event_type=EventType.PROGRESS, data={"percent": 50}, timestamp=100.0
    )
    bridge._on_progress(event)

    assert dashboard.progress == 50


def test_event_bridge_updates_real_dashboard_contract(monkeypatch):
    """EventBridge should adapt event payloads to PipelineDashboard methods."""
    from subtap.metrics.profiler import PipelineProfiler
    from subtap.ui.dashboard import PipelineDashboard

    bus = EventBus()
    dashboard = PipelineDashboard(bus, PipelineProfiler(bus))
    bridge = EventBridge(bus, dashboard)

    captured = {}
    monkeypatch.setattr(
        dashboard,
        "update_chunk",
        lambda current, total: captured.update(chunk=(current, total)),
    )
    monkeypatch.setattr(
        dashboard,
        "update_progress",
        lambda progress: captured.update(progress=progress),
    )

    bridge._on_chunk_end(
        PipelineEvent(
            event_type=EventType.CHUNK_END,
            data={"chunk_id": 2, "chunks_total": 5},
            timestamp=100.0,
        )
    )
    bridge._on_progress(
        PipelineEvent(
            event_type=EventType.PROGRESS,
            data={"progress": 40},
            timestamp=100.0,
        )
    )

    assert captured["chunk"] == (2, 5)
    assert captured["progress"] == 40


def test_dashboard_streaming_event_refreshes_visible_panels(monkeypatch):
    """A single streaming event should update all visible panels once allowed."""
    from subtap.metrics.profiler import PipelineProfiler
    from subtap.ui.dashboard import (
        ModelPanel,
        PipelineDashboard,
        ProgressPanel,
        StagePanel,
    )

    bus = EventBus()
    dashboard = PipelineDashboard(bus, PipelineProfiler(bus))

    captured = {}

    class FakeStage:
        def update_stage(self, stage):
            captured["stage"] = stage

    class FakeProgress:
        def update_progress(self, progress):
            captured["progress"] = progress

    class FakeModel:
        def update_model(self, model, latency):
            captured["model"] = (model, latency)

    panels = {
        StagePanel: FakeStage(),
        ProgressPanel: FakeProgress(),
        ModelPanel: FakeModel(),
    }
    monkeypatch.setattr(dashboard, "query_one", lambda panel: panels[panel])

    dashboard.update_streaming_event(
        {"stage": "asr", "progress": 30, "model": "asr_0.6b", "duration_sec": 1.5}
    )

    assert captured["stage"] == "asr"
    assert captured["progress"] == 30
    assert captured["model"] == ("asr_0.6b", 1.5)


def test_cli_run_help():
    """Test CLI run command help works."""
    from typer.testing import CliRunner
    from subtap.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
