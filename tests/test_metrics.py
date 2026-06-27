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

    # 启动事件循环
    task = asyncio.create_task(bus.start())

    # 发布事件
    await bus.publish(event)

    # 等待处理
    await asyncio.sleep(0.1)
    bus.stop()
    await task

    assert len(received) == 1
    assert received[0].data == {"stage": "asr"}


@pytest.mark.asyncio
async def test_event_bus_full_flow():
    """Test complete event flow: publish -> queue -> dispatch."""
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(EventType.STAGE_START, handler)

    # 启动事件循环
    task = asyncio.create_task(bus.start())

    # 发布事件
    event = PipelineEvent(event_type=EventType.STAGE_START, data={"test": True})
    await bus.publish(event)

    # 等待处理
    await asyncio.sleep(0.1)
    bus.stop()
    await task

    assert len(received) == 1
    assert received[0].data == {"test": True}


@pytest.mark.asyncio
async def test_event_bus_queue_full():
    """Test queue full behavior."""
    bus = EventBus(buffer_size=2)

    # 发布超过缓冲大小的事件
    for i in range(3):
        event = PipelineEvent(event_type=EventType.STAGE_START, data={"i": i})
        await bus.publish(event)

    # 队列应该满，但不会阻塞
    assert bus._queue.qsize() == 2


@pytest.mark.asyncio
async def test_async_callback():
    """Test async callback handling."""
    bus = EventBus()
    received = []

    async def async_handler(event):
        received.append(event)

    bus.subscribe(EventType.STAGE_START, async_handler)

    task = asyncio.create_task(bus.start())
    event = PipelineEvent(event_type=EventType.STAGE_START)
    await bus.publish(event)

    await asyncio.sleep(0.1)
    bus.stop()
    await task

    assert len(received) == 1


def test_profiler_init():
    """Test PipelineProfiler initialization."""
    from subtap.metrics.profiler import PipelineProfiler

    bus = EventBus()
    profiler = PipelineProfiler(bus)
    assert profiler.event_bus == bus
    assert profiler._stage_times == {}


def test_profiler_wrap_pipeline():
    """Test PipelineProfiler wrap_pipeline."""
    from subtap.metrics.profiler import PipelineProfiler

    bus = EventBus()
    profiler = PipelineProfiler(bus)

    class MockPipeline:
        def run_stage(self, stage_name, **kwargs):
            return {"result": "ok"}

    pipeline = MockPipeline()
    profiler.wrap_pipeline(pipeline)

    # Verify wrap was applied
    assert hasattr(pipeline.run_stage, '__wrapped__')


def test_profiler_get_report():
    """Test PipelineProfiler get_report."""
    from subtap.metrics.profiler import PipelineProfiler

    bus = EventBus()
    profiler = PipelineProfiler(bus)
    profiler._stage_times = {"asr": 5.2, "clean": 1.1}

    report = profiler.get_report()
    assert report["total_time"] == pytest.approx(6.3)
    assert report["stages"]["asr"] == 5.2
