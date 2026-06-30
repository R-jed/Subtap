import asyncio
import json
import threading

import pytest
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
        event_type=EventType.STAGE_START, data={"stage": "asr"}, timestamp=1234567890.0
    )
    assert event.event_type == EventType.STAGE_START
    assert event.data == {"stage": "asr"}
    assert event.timestamp == 1234567890.0


def test_event_bus_writes_event_log_jsonl(tmp_path):
    """EventBus 应把 pipeline 事件写入 JSONL，供独立观察者进程读取。"""
    bus = EventBus(log_path=tmp_path / "run.log.jsonl")

    bus.publish_nowait(
        PipelineEvent(
            event_type=EventType.PROGRESS,
            data={"stage": "asr", "progress": 30},
            timestamp=123.0,
        )
    )

    rows = (tmp_path / "run.log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert payload["event_type"] == "progress"
    assert payload["data"] == {"stage": "asr", "progress": 30}
    assert payload["timestamp"] == 123.0


def test_event_bus_subscribe():
    """Test EventBus subscribe."""
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(EventType.STAGE_START, handler)
    assert EventType.STAGE_START in bus._subscribers
    assert handler in bus._subscribers[EventType.STAGE_START]


def test_profiler_wrap_pipeline_without_running_event_loop():
    """Profiler should work when CLI runs the pipeline synchronously."""
    from subtap.metrics.profiler import PipelineProfiler

    class FakePipeline:
        def run_stage(self, stage_name: str, **kwargs):
            return {"stage": stage_name, "kwargs": kwargs}

    bus = EventBus()
    pipeline = FakePipeline()
    profiler = PipelineProfiler(bus)
    profiler.wrap_pipeline(pipeline)

    result = pipeline.run_stage("prepare", input_path="input.wav")

    assert result["stage"] == "prepare"
    assert bus._queue.qsize() == 2


@pytest.mark.asyncio
async def test_event_bus_publish():
    """Test EventBus publish."""
    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe(EventType.STAGE_START, handler)

    event = PipelineEvent(
        event_type=EventType.STAGE_START, data={"stage": "asr"}, timestamp=1234567890.0
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
async def test_event_bus_publish_from_worker_thread_uses_loop_threadsafe(monkeypatch):
    """TUI 主循环消费事件时，后台推理线程投递事件必须走线程安全入口。"""
    bus = EventBus()
    received = []
    scheduled = []
    loop = asyncio.get_running_loop()
    original_call_soon_threadsafe = loop.call_soon_threadsafe

    def handler(event):
        received.append(event)

    def spy_call_soon_threadsafe(callback, *args, context=None):
        scheduled.append((callback, args))
        if context is None:
            return original_call_soon_threadsafe(callback, *args)
        return original_call_soon_threadsafe(callback, *args, context=context)

    monkeypatch.setattr(loop, "call_soon_threadsafe", spy_call_soon_threadsafe)
    bus.subscribe(EventType.PROGRESS, handler)
    task = asyncio.create_task(bus.start())
    await asyncio.sleep(0)

    event = PipelineEvent(event_type=EventType.PROGRESS, data={"progress": 30})
    worker = threading.Thread(target=bus.publish_nowait, args=(event,))
    worker.start()
    worker.join(timeout=1)

    for _ in range(20):
        if received:
            break
        await asyncio.sleep(0.01)

    bus.stop()
    await task

    assert scheduled
    assert len(received) == 1
    assert received[0].data == {"progress": 30}


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
    assert hasattr(pipeline.run_stage, "__wrapped__")


def test_profiler_get_report():
    """Test PipelineProfiler get_report."""
    from subtap.metrics.profiler import PipelineProfiler

    bus = EventBus()
    profiler = PipelineProfiler(bus)
    profiler._stage_times = {"asr": 5.2, "clean": 1.1}

    report = profiler.get_report()
    assert report["total_time"] == pytest.approx(6.3)
    assert report["stages"]["asr"] == 5.2


def test_chunk_tracer_init():
    """Test ChunkTracer initialization."""
    from subtap.metrics.chunk_trace import ChunkTracer

    bus = EventBus()
    tracer = ChunkTracer(bus, window_size=5)
    assert tracer._window_size == 5
    assert len(tracer._latency_window) == 0


def test_chunk_tracer_on_chunk_end():
    """Test ChunkTracer on_chunk_end."""
    from subtap.metrics.chunk_trace import ChunkTracer

    bus = EventBus()
    tracer = ChunkTracer(bus, window_size=5)

    event = PipelineEvent(
        event_type=EventType.CHUNK_END,
        data={"chunk_id": 0, "start_time": 100.0, "end_time": 100.3, "model": "asr"},
        timestamp=100.3,
    )

    tracer.on_chunk_end(event)

    assert len(tracer._chunks) == 1
    assert tracer._chunks[0]["id"] == 0
    assert tracer._chunks[0]["time"] == pytest.approx(0.3)
    assert len(tracer._latency_window) == 1


def test_chunk_tracer_get_slow_chunks():
    """Test ChunkTracer get_slow_chunks."""
    from subtap.metrics.chunk_trace import ChunkTracer

    bus = EventBus()
    tracer = ChunkTracer(bus, window_size=5)

    # Add normal chunks
    for i in range(3):
        event = PipelineEvent(
            event_type=EventType.CHUNK_END,
            data={
                "chunk_id": i,
                "start_time": 100.0,
                "end_time": 100.2,
                "model": "asr",
            },
            timestamp=100.2,
        )
        tracer.on_chunk_end(event)

    # Add slow chunk
    event = PipelineEvent(
        event_type=EventType.CHUNK_END,
        data={"chunk_id": 3, "start_time": 100.0, "end_time": 100.5, "model": "asr"},
        timestamp=100.5,
    )
    tracer.on_chunk_end(event)

    slow_chunks = tracer.get_slow_chunks(threshold=1.5)
    assert len(slow_chunks) == 1
    assert slow_chunks[0]["id"] == 3


def test_metrics_config_defaults():
    """Test MetricsConfig default values."""
    from subtap.schemas.config import MetricsConfig

    config = MetricsConfig()
    assert config.enabled is True
    assert config.slow_threshold == 1.5
    assert config.output_path == "performance.json"


def test_metrics_config_custom():
    """Test MetricsConfig custom values."""
    from subtap.schemas.config import MetricsConfig

    config = MetricsConfig(enabled=False, slow_threshold=2.0)
    assert config.enabled is False
    assert config.slow_threshold == 2.0


def test_full_metrics_flow():
    """Test complete metrics flow."""
    from subtap.metrics.events import EventBus, EventType, PipelineEvent
    from subtap.metrics.profiler import PipelineProfiler
    from subtap.metrics.chunk_trace import ChunkTracer

    # Create components
    bus = EventBus()
    profiler = PipelineProfiler(bus)
    tracer = ChunkTracer(bus, window_size=5)

    # Simulate chunk events
    for i in range(5):
        latency = 0.2 if i < 4 else 0.5  # Last chunk is slow
        event = PipelineEvent(
            event_type=EventType.CHUNK_END,
            data={
                "chunk_id": i,
                "start_time": 100.0,
                "end_time": 100.0 + latency,
                "model": "asr",
            },
            timestamp=100.0 + latency,
        )
        tracer.on_chunk_end(event)

    # Check slow chunks
    slow_chunks = tracer.get_slow_chunks(threshold=1.5)
    assert len(slow_chunks) == 1
    assert slow_chunks[0]["id"] == 4

    # Generate report
    profiler._stage_times = {"asr": 5.2, "clean": 1.1}
    report = profiler.get_report()
    assert report["total_time"] == pytest.approx(6.3)
