"""Tests for metrics system."""

import pytest
import asyncio
from subtap.metrics.events import EventType, PipelineEvent, EventBus


def test_event_type_enum():
    """Test EventType enum values."""
    assert EventType.STAGE_START.value == "stage_start"
    assert EventType.STAGE_END.value == "stage_end"
    assert EventType.CHUNK_START.value == "chunk_start"
    assert EventType.CHUNK_END.value == "chunk_end"


def test_pipeline_event_creation():
    """Test PipelineEvent creation."""
    event = PipelineEvent(
        event_type=EventType.STAGE_START,
        data={"stage": "asr"},
        timestamp=1234567890.0
    )
    assert event.event_type == EventType.STAGE_START
    assert event.data == {"stage": "asr"}
    assert event.timestamp == 1234567890.0


def test_event_bus_subscribe():
    """Test EventBus subscribe."""
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(EventType.STAGE_START, handler)
    assert EventType.STAGE_START in bus._subscribers
    assert handler in bus._subscribers[EventType.STAGE_START]


@pytest.mark.asyncio
async def test_event_bus_publish():
    """Test EventBus publish."""
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(EventType.STAGE_START, handler)

    event = PipelineEvent(
        event_type=EventType.STAGE_START,
        data={"stage": "asr"},
        timestamp=1234567890.0
    )

    await bus.publish(event)
    await bus._dispatch(event)

    assert len(received) == 1
    assert received[0].data == {"stage": "asr"}
