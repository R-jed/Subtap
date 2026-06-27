"""Tests for dashboard system."""

import pytest
from subtap.metrics.events import EventBus, EventType, PipelineEvent
from subtap.ui.event_bridge import EventBridge


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
