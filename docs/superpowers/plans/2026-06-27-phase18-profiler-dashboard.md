# Phase 18: Performance Profiler + TUI Execution Dashboard 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建"可观测执行系统 + 中文 TUI + chunk 级性能分析"

**架构：** 
- EventBus + Queue 事件系统
- Profiler 装饰器包裹 pipeline
- ChunkTracer 滑动窗口追踪
- Textual Dashboard 实时显示

**技术栈：** Python 3.10+, asyncio, Textual, Pydantic v2

---

## 文件结构

### 需要创建的文件

| 文件 | 职责 |
|------|------|
| `src/subtap/metrics/__init__.py` | metrics 模块初始化 |
| `src/subtap/metrics/events.py` | 事件定义 + EventBus |
| `src/subtap/metrics/profiler.py` | PipelineProfiler |
| `src/subtap/metrics/chunk_trace.py` | ChunkTracer |
| `src/subtap/metrics/slow_detector.py` | SlowChunkDetector |
| `src/subtap/ui/dashboard.py` | PipelineDashboard (Textual) |
| `src/subtap/ui/event_bridge.py` | EventBridge |
| `tests/test_metrics.py` | metrics 测试 |
| `tests/test_dashboard.py` | dashboard 测试 |

### 需要修改的文件

| 文件 | 职责 |
|------|------|
| `src/subtap/schemas/config.py` | 添加 MetricsConfig |
| `src/subtap/cli.py` | 添加 --tui 参数 |

---

## 任务 1：创建事件系统基础

**文件：**
- 创建：`src/subtap/metrics/__init__.py`
- 创建：`src/subtap/metrics/events.py`
- 测试：`tests/test_metrics.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_metrics.py
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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_metrics.py -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.metrics'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/metrics/__init__.py
"""Metrics system for Subtap."""

from subtap.metrics.events import EventType, PipelineEvent, EventBus

__all__ = ["EventType", "PipelineEvent", "EventBus"]
```

```python
# src/subtap/metrics/events.py
"""Event system for pipeline metrics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(Enum):
    """Pipeline event types."""
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    CHUNK_START = "chunk_start"
    CHUNK_END = "chunk_end"
    PROGRESS = "progress"
    MODEL_LOAD = "model_load"


@dataclass
class PipelineEvent:
    """Pipeline event data."""
    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


class EventBus:
    """Async event bus with queue buffer."""

    def __init__(self, buffer_size: int = 100):
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=buffer_size)
        self._running = False

    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        """Subscribe to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    async def publish(self, event: PipelineEvent) -> None:
        """Non-blocking publish to queue."""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop oldest event to prevent blocking

    async def start(self) -> None:
        """Start event processing loop."""
        self._running = True
        while self._running:
            event = await self._queue.get()
            await self._dispatch(event)

    async def _dispatch(self, event: PipelineEvent) -> None:
        """Dispatch event to subscribers."""
        for callback in self._subscribers.get(event.event_type, []):
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)

    def stop(self) -> None:
        """Stop event processing loop."""
        self._running = False
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_metrics.py -v`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/metrics/__init__.py src/subtap/metrics/events.py tests/test_metrics.py
git commit -m "feat: add event system for metrics"
```

---

## 任务 2：创建 PipelineProfiler

**文件：**
- 创建：`src/subtap/metrics/profiler.py`
- 测试：`tests/test_metrics.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_metrics.py
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
    assert report["total_time"] == 6.3
    assert report["stages"]["asr"] == 5.2
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_metrics.py::test_profiler_init -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.metrics.profiler'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/metrics/profiler.py
"""Pipeline performance profiler."""

from __future__ import annotations

import time
from typing import Any, Callable

from subtap.metrics.events import EventBus, EventType, PipelineEvent


class PipelineProfiler:
    """Profiles pipeline execution with stage and chunk timing."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._stage_times: dict[str, float] = {}
        self._chunk_times: list[dict] = []
        self._start_time: float = 0

    def wrap_pipeline(self, pipeline: Any) -> None:
        """Wrap pipeline.run_stage with profiling."""
        original_run_stage = pipeline.run_stage

        def wrapped_run_stage(stage_name: str, **kwargs) -> Any:
            # Publish stage start event
            self.event_bus._dispatch(PipelineEvent(
                event_type=EventType.STAGE_START,
                data={"stage": stage_name},
                timestamp=time.time()
            ))

            stage_start = time.time()
            result = original_run_stage(stage_name, **kwargs)
            stage_end = time.time()

            # Record stage time
            self._stage_times[stage_name] = stage_end - stage_start

            # Publish stage end event
            self.event_bus._dispatch(PipelineEvent(
                event_type=EventType.STAGE_END,
                data={"stage": stage_name, "duration": stage_end - stage_start},
                timestamp=time.time()
            ))

            return result

        # Mark as wrapped for testing
        wrapped_run_stage.__wrapped__ = True
        pipeline.run_stage = wrapped_run_stage

    def get_report(self) -> dict:
        """Generate performance report."""
        return {
            "total_time": sum(self._stage_times.values()),
            "stages": self._stage_times,
            "chunks": self._chunk_times,
        }
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_metrics.py -v -k profiler`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/metrics/profiler.py tests/test_metrics.py
git commit -m "feat: add PipelineProfiler"
```

---

## 任务 3：创建 ChunkTracer

**文件：**
- 创建：`src/subtap/metrics/chunk_trace.py`
- 测试：`tests/test_metrics.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_metrics.py
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
        timestamp=100.3
    )
    
    tracer.on_chunk_end(event)
    
    assert len(tracer._chunks) == 1
    assert tracer._chunks[0]["id"] == 0
    assert tracer._chunks[0]["time"] == 0.3
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
            data={"chunk_id": i, "start_time": 100.0, "end_time": 100.2, "model": "asr"},
            timestamp=100.2
        )
        tracer.on_chunk_end(event)
    
    # Add slow chunk
    event = PipelineEvent(
        event_type=EventType.CHUNK_END,
        data={"chunk_id": 3, "start_time": 100.0, "end_time": 100.5, "model": "asr"},
        timestamp=100.5
    )
    tracer.on_chunk_end(event)
    
    slow_chunks = tracer.get_slow_chunks(threshold=1.5)
    assert len(slow_chunks) == 1
    assert slow_chunks[0]["id"] == 3
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_metrics.py::test_chunk_tracer_init -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.metrics.chunk_trace'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/metrics/chunk_trace.py
"""Chunk-level performance tracing."""

from __future__ import annotations

from collections import deque

from subtap.metrics.events import EventBus, EventType, PipelineEvent


class ChunkTracer:
    """Traces chunk-level performance with sliding window average."""

    def __init__(self, event_bus: EventBus, window_size: int = 10):
        self.event_bus = event_bus
        self._window_size = window_size
        self._chunks: list[dict] = []
        self._latency_window: deque[float] = deque(maxlen=window_size)

    def on_chunk_end(self, event: PipelineEvent) -> None:
        """Record chunk end with sliding window average."""
        chunk_data = event.data
        latency = chunk_data["end_time"] - chunk_data["start_time"]

        # Add to sliding window
        self._latency_window.append(latency)

        # Calculate sliding window average
        avg_latency = sum(self._latency_window) / len(self._latency_window)

        # Record chunk
        self._chunks.append({
            "id": chunk_data["chunk_id"],
            "time": latency,
            "avg": avg_latency,
            "model": chunk_data.get("model", "unknown"),
        })

    def get_slow_chunks(self, threshold: float = 1.5) -> list[dict]:
        """Get chunks exceeding threshold * average latency."""
        if not self._latency_window:
            return []

        avg = sum(self._latency_window) / len(self._latency_window)
        return [
            chunk for chunk in self._chunks
            if chunk["time"] > avg * threshold
        ]
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_metrics.py -v -k chunk`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/metrics/chunk_trace.py tests/test_metrics.py
git commit -m "feat: add ChunkTracer with sliding window"
```

---

## 任务 4：创建 SlowChunkDetector

**文件：**
- 创建：`src/subtap/metrics/slow_detector.py`
- 测试：`tests/test_metrics.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_metrics.py
def test_slow_detector_init():
    """Test SlowChunkDetector initialization."""
    from subtap.metrics.slow_detector import SlowChunkDetector
    
    detector = SlowChunkDetector(threshold=2.0)
    assert detector.threshold == 2.0
    assert detector._slow_chunks == []


def test_slow_detector_check():
    """Test SlowChunkDetector check."""
    from subtap.metrics.slow_detector import SlowChunkDetector
    
    detector = SlowChunkDetector(threshold=1.5)
    
    # Normal chunk
    assert detector.check(0.2, 0.2) is False
    
    # Slow chunk
    assert detector.check(0.5, 0.2) is True


def test_slow_detector_add_slow_chunk():
    """Test SlowChunkDetector add_slow_chunk."""
    from subtap.metrics.slow_detector import SlowChunkDetector
    
    detector = SlowChunkDetector(threshold=1.5)
    detector.add_slow_chunk(chunk_id=1, latency=0.5, avg=0.2)
    
    assert len(detector._slow_chunks) == 1
    assert detector._slow_chunks[0]["id"] == 1
    assert detector._slow_chunks[0]["threshold"] == 1.5


def test_slow_detector_get_slow_chunks():
    """Test SlowChunkDetector get_slow_chunks."""
    from subtap.metrics.slow_detector import SlowChunkDetector
    
    detector = SlowChunkDetector(threshold=1.5)
    detector.add_slow_chunk(chunk_id=1, latency=0.5, avg=0.2)
    detector.add_slow_chunk(chunk_id=2, latency=0.6, avg=0.3)
    
    slow_chunks = detector.get_slow_chunks()
    assert len(slow_chunks) == 2
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_metrics.py::test_slow_detector_init -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.metrics.slow_detector'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/metrics/slow_detector.py
"""Slow chunk detection."""

from __future__ import annotations


class SlowChunkDetector:
    """Detects chunks with latency exceeding threshold * average."""

    def __init__(self, threshold: float = 1.5):
        self.threshold = threshold
        self._slow_chunks: list[dict] = []

    def check(self, chunk_latency: float, avg_latency: float) -> bool:
        """Check if chunk latency exceeds threshold."""
        return chunk_latency > avg_latency * self.threshold

    def add_slow_chunk(self, chunk_id: int, latency: float, avg: float) -> None:
        """Record a slow chunk."""
        self._slow_chunks.append({
            "id": chunk_id,
            "time": latency,
            "avg": avg,
            "threshold": self.threshold,
        })

    def get_slow_chunks(self) -> list[dict]:
        """Get all recorded slow chunks."""
        return self._slow_chunks
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_metrics.py -v -k slow`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/metrics/slow_detector.py tests/test_metrics.py
git commit -m "feat: add SlowChunkDetector"
```

---

## 任务 5：添加 MetricsConfig 配置

**文件：**
- 修改：`src/subtap/schemas/config.py`
- 测试：`tests/test_metrics.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_metrics.py
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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_metrics.py::test_metrics_config_defaults -v`
预期：FAIL，报错 "ImportError: cannot import name 'MetricsConfig'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/schemas/config.py
# 在现有配置类后添加

class MetricsConfig(BaseModel):
    """Performance metrics configuration."""

    enabled: bool = True
    slow_threshold: float = 1.5
    output_path: str = "performance.json"


class SubtapConfig(BaseModel):
    """Root configuration for Subtap."""

    audio: AudioConfig = Field(default_factory=AudioConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    clean: CleanConfig = Field(default_factory=CleanConfig)
    align: AlignConfig = Field(default_factory=AlignConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)  # 新增
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_metrics.py -v -k config`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/schemas/config.py tests/test_metrics.py
git commit -m "feat: add MetricsConfig configuration"
```

---

## 任务 6：创建 EventBridge

**文件：**
- 创建：`src/subtap/ui/event_bridge.py`
- 测试：`tests/test_dashboard.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_dashboard.py
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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_dashboard.py::test_event_bridge_init -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.ui.event_bridge'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/ui/event_bridge.py
"""Event bridge connecting metrics to UI."""

from __future__ import annotations

from typing import Any

from subtap.metrics.events import EventBus, EventType, PipelineEvent


class EventBridge:
    """Bridges pipeline events to dashboard updates."""

    def __init__(self, event_bus: EventBus, dashboard: Any):
        self.event_bus = event_bus
        self.dashboard = dashboard

    def connect(self) -> None:
        """Connect events to UI updates."""
        self.event_bus.subscribe(EventType.STAGE_START, self._on_stage_start)
        self.event_bus.subscribe(EventType.STAGE_END, self._on_stage_end)
        self.event_bus.subscribe(EventType.CHUNK_END, self._on_chunk_end)
        self.event_bus.subscribe(EventType.PROGRESS, self._on_progress)

    def _on_stage_start(self, event: PipelineEvent) -> None:
        """Handle stage start event."""
        if self.dashboard and hasattr(self.dashboard, 'update_stage'):
            self.dashboard.update_stage(event.data["stage"])

    def _on_stage_end(self, event: PipelineEvent) -> None:
        """Handle stage end event."""
        if self.dashboard and hasattr(self.dashboard, 'update_stage_complete'):
            self.dashboard.update_stage_complete(
                event.data["stage"],
                event.data["duration"]
            )

    def _on_chunk_end(self, event: PipelineEvent) -> None:
        """Handle chunk end event."""
        if self.dashboard and hasattr(self.dashboard, 'update_chunk'):
            self.dashboard.update_chunk(event.data)

    def _on_progress(self, event: PipelineEvent) -> None:
        """Handle progress event."""
        if self.dashboard and hasattr(self.dashboard, 'update_progress'):
            self.dashboard.update_progress(event.data)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_dashboard.py -v -k bridge`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/event_bridge.py tests/test_dashboard.py
git commit -m "feat: add EventBridge"
```

---

## 任务 7：创建 Textual Dashboard

**文件：**
- 创建：`src/subtap/ui/dashboard.py`
- 测试：`tests/test_dashboard.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_dashboard.py
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
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_dashboard.py::test_dashboard_init -v`
预期：FAIL，报错 "ModuleNotFoundError: No module named 'subtap.ui.dashboard'"

- [ ] **步骤 3：编写最少实现代码**

```python
# src/subtap/ui/dashboard.py
"""Textual dashboard for pipeline execution."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ProgressBar

from subtap.metrics.events import EventBus
from subtap.metrics.profiler import PipelineProfiler

# Chinese stage name mapping
STAGE_CN = {
    "prepare": "音频标准化",
    "chunk": "音频切段",
    "asr": "语音识别",
    "clean": "文本优化",
    "segment": "智能断句",
    "align": "字幕对齐",
    "export": "字幕导出",
}


class StagePanel(Static):
    """Current stage display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stage = "等待中"

    def update_stage(self, stage: str) -> None:
        """Update current stage."""
        self._stage = STAGE_CN.get(stage, stage)
        self.update(f"当前阶段：{self._stage}")


class ProgressPanel(Static):
    """Progress display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._progress = 0

    def update_progress(self, progress: int) -> None:
        """Update progress percentage."""
        self._progress = progress
        bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
        self.update(f"进度：{bar} {progress}%")


class ChunkPanel(Static):
    """Chunk progress display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current = 0
        self._total = 0

    def update_chunk(self, current: int, total: int) -> None:
        """Update chunk progress."""
        self._current = current
        self._total = total
        self.update(f"当前 Chunk：{current} / {total}")


class ModelPanel(Static):
    """Model info display."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model = "未知"
        self._latency = 0.0

    def update_model(self, model: str, latency: float) -> None:
        """Update model info."""
        self._model = model
        self._latency = latency
        self.update(f"当前模型：{self._model}\n延迟：{latency:.2f}s / chunk")


class PipelineDashboard(App):
    """Textual dashboard for pipeline execution."""

    def __init__(self, event_bus: EventBus, profiler: PipelineProfiler, **kwargs):
        super().__init__(**kwargs)
        self.event_bus = event_bus
        self.profiler = profiler
        self._update_throttle = 0.05  # 50ms throttle
        self._last_update = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield StagePanel()
        yield ProgressPanel()
        yield ChunkPanel()
        yield ModelPanel()
        yield Footer()

    async def on_mount(self) -> None:
        """Start event processing."""
        self.run_worker(self.event_bus.start())

    def update_stage(self, stage: str) -> None:
        """Update stage display."""
        stage_panel = self.query_one(StagePanel)
        stage_panel.update_stage(stage)

    def update_progress(self, progress: int) -> None:
        """Update progress display."""
        progress_panel = self.query_one(ProgressPanel)
        progress_panel.update_progress(progress)

    def update_chunk(self, current: int, total: int) -> None:
        """Update chunk display."""
        chunk_panel = self.query_one(ChunkPanel)
        chunk_panel.update_chunk(current, total)

    def update_model(self, model: str, latency: float) -> None:
        """Update model display."""
        model_panel = self.query_one(ModelPanel)
        model_panel.update_model(model, latency)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_dashboard.py -v -k dashboard`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/ui/dashboard.py tests/test_dashboard.py
git commit -m "feat: add Textual PipelineDashboard"
```

---

## 任务 8：集成到 CLI

**文件：**
- 修改：`src/subtap/cli.py`
- 测试：`tests/test_dashboard.py`

- [ ] **步骤 1：编写失败的测试**

```python
# tests/test_dashboard.py
def test_cli_run_has_tui_flag():
    """Test CLI run command has --tui flag."""
    from typer.testing import CliRunner
    from subtap.cli import app
    
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--tui" in result.output
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest tests/test_dashboard.py::test_cli_run_has_tui_flag -v`
预期：PASS (help command works)

- [ ] **步骤 3：修改 CLI 集成**

```python
# src/subtap/cli.py
@app.command()
def run(
    input_path: Path = typer.Argument(..., help="输入媒体文件路径"),
    # ... 其他参数
    tui: bool = typer.Option(True, "--tui/--no-tui", help="启用 TUI 界面"),
) -> None:
    """运行完整字幕生成流程"""
    from subtap.schemas.config import load_config
    from subtap.core.pipeline import Pipeline
    from subtap.metrics.events import EventBus
    from subtap.metrics.profiler import PipelineProfiler
    
    # ... 现有代码 ...
    
    # 创建 Event Bus 和 Profiler
    event_bus = EventBus()
    profiler = PipelineProfiler(event_bus)
    profiler.wrap_pipeline(pipeline)
    
    if tui:
        from subtap.ui.dashboard import PipelineDashboard
        from subtap.ui.event_bridge import EventBridge
        
        dashboard = PipelineDashboard(event_bus, profiler)
        bridge = EventBridge(event_bus, dashboard)
        bridge.connect()
        dashboard.run()
    else:
        # 普通执行
        ...
```

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest tests/test_dashboard.py -v -k cli`
预期：PASS

- [ ] **步骤 5：Commit**

```bash
git add src/subtap/cli.py tests/test_dashboard.py
git commit -m "feat: integrate profiler and dashboard to CLI"
```

---

## 任务 9：完整集成测试

**文件：**
- 测试：`tests/test_metrics.py`
- 测试：`tests/test_dashboard.py`

- [ ] **步骤 1：编写集成测试**

```python
# tests/test_metrics.py
def test_full_metrics_flow():
    """Test complete metrics flow."""
    from subtap.metrics.events import EventBus, EventType, PipelineEvent
    from subtap.metrics.profiler import PipelineProfiler
    from subtap.metrics.chunk_trace import ChunkTracer
    from subtap.metrics.slow_detector import SlowChunkDetector
    
    # Create components
    bus = EventBus()
    profiler = PipelineProfiler(bus)
    tracer = ChunkTracer(bus, window_size=5)
    detector = SlowChunkDetector(threshold=1.5)
    
    # Simulate chunk events
    for i in range(5):
        latency = 0.2 if i < 4 else 0.5  # Last chunk is slow
        event = PipelineEvent(
            event_type=EventType.CHUNK_END,
            data={"chunk_id": i, "start_time": 100.0, "end_time": 100.0 + latency, "model": "asr"},
            timestamp=100.0 + latency
        )
        tracer.on_chunk_end(event)
    
    # Check slow chunks
    slow_chunks = tracer.get_slow_chunks(threshold=1.5)
    assert len(slow_chunks) == 1
    assert slow_chunks[0]["id"] == 4
    
    # Generate report
    profiler._stage_times = {"asr": 5.2, "clean": 1.1}
    report = profiler.get_report()
    assert report["total_time"] == 6.3
```

- [ ] **步骤 2：运行测试验证**

运行：`pytest tests/test_metrics.py::test_full_metrics_flow -v`
预期：PASS

- [ ] **步骤 3：运行所有测试**

运行：`pytest -v`
预期：所有测试通过

- [ ] **步骤 4：Commit**

```bash
git add tests/test_metrics.py tests/test_dashboard.py
git commit -m "test: add full metrics flow integration test"
```

---

## 任务 10：最终验证

**文件：** 无

- [ ] **步骤 1：运行所有测试**

运行：`pytest -v`
预期：所有测试通过

- [ ] **步骤 2：运行 metrics 测试**

运行：`pytest tests/test_metrics.py -v`
预期：所有 metrics 测试通过

- [ ] **步骤 3：运行 dashboard 测试**

运行：`pytest tests/test_dashboard.py -v`
预期：所有 dashboard 测试通过

- [ ] **步骤 4：手动测试 CLI**

```bash
# 测试 --tui 参数
subtap run --help

# 测试 performance.json 生成
subtap run video.mp3 --no-tui
```

- [ ] **步骤 5：最终 Commit**

```bash
git add -A
git commit -m "feat: Phase 18 Profiler + Dashboard complete"
```

---

## 验收标准

1. ✔ TUI 实时显示 pipeline 状态
2. ✔ chunk 级进度可见
3. ✔ performance.json 生成
4. ✔ 中文状态完整
5. ✔ 无日志刷屏
6. ✔ pipeline 无侵入
7. ✔ UI 与 core 完全解耦
8. ✔ 所有测试通过
