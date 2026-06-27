# Phase 18: Performance Profiler + TUI Execution Dashboard 设计规格

## 概述

构建"可观测执行系统 + 中文 TUI + chunk 级性能分析"。

## 设计决策

| 决策点 | 选择 |
|--------|------|
| 数据获取方式 | 装饰器包裹 pipeline.run_stage() |
| UI 技术栈 | Textual（不是 Rich） |
| 刷新方式 | 事件驱动 |
| 事件机制 | EventBus + Queue |
| slow chunk 阈值 | 可配置（默认 1.5 倍） |
| slow chunk 通知 | UI 高亮 + 延迟通知（不弹窗） |
| UI 更新节流 | 50-100ms throttle |

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Pipeline Core                         │
│  (不修改，通过装饰器包裹)                                │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Event Bus                              │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │
│  │  StageEvent │ │ ChunkEvent  │ │  ProgressEvent  │  │
│  └─────────────┘ └─────────────┘ └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Metrics Layer                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │
│  │  Profiler   │ │ ChunkTracer │ │  SlowDetector   │  │
│  └─────────────┘ └─────────────┘ └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    TUI Layer                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │
│  │  Dashboard  │ │ EventBridge │ │  ProgressPanel  │  │
│  └─────────────┘ └─────────────┘ └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 文件结构

```
src/subtap/
  ├── metrics/
  │   ├── __init__.py
  │   ├── profiler.py          # PipelineProfiler
  │   ├── chunk_trace.py       # ChunkTracer
  │   ├── slow_detector.py     # SlowChunkDetector
  │   └── events.py            # 事件定义 + EventBus
  ├── ui/
  │   ├── dashboard.py         # PipelineDashboard (Textual)
  │   ├── event_bridge.py      # EventBridge
  │   └── (现有文件保持不变)
  └── cli.py                   # 添加 --tui 参数
```

## 实现优先级

| 优先级 | 任务 | 文件 |
|--------|------|------|
| 🥇 Step 1 | EventBus 基础 | `metrics/events.py` |
| 🥈 Step 2 | Profiler + wrap_pipeline | `metrics/profiler.py` |
| 🥉 Step 3 | ChunkTracer + slow detection | `metrics/chunk_trace.py` + `metrics/slow_detector.py` |
| 🏁 Step 4 | EventBridge | `ui/event_bridge.py` |
| 🧠 Step 5 | Textual Dashboard | `ui/dashboard.py` |

## 核心组件

### EventBus

```python
# src/subtap/metrics/events.py
import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

class EventType(Enum):
    STAGE_START = "stage_start"
    STAGE_END = "stage_end"
    CHUNK_START = "chunk_start"
    CHUNK_END = "chunk_end"
    PROGRESS = "progress"
    MODEL_LOAD = "model_load"

@dataclass
class PipelineEvent:
    event_type: EventType
    data: dict[str, Any]
    timestamp: float

class EventBus:
    def __init__(self, buffer_size: int = 100):
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._queue: asyncio.Queue[PipelineEvent] = asyncio.Queue(maxsize=buffer_size)
        self._running = False
    
    async def publish(self, event: PipelineEvent) -> None:
        """非阻塞发布，放入队列"""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass
    
    async def start(self) -> None:
        """启动事件处理循环"""
        self._running = True
        while self._running:
            event = await self._queue.get()
            await self._dispatch(event)
    
    async def _dispatch(self, event: PipelineEvent) -> None:
        """分发事件给订阅者"""
        for callback in self._subscribers.get(event.event_type, []):
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
```

### PipelineProfiler

```python
# src/subtap/metrics/profiler.py
import time
from typing import Any

class PipelineProfiler:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self._stage_times: dict[str, float] = {}
        self._chunk_times: list[dict] = []
        self._start_time: float = 0
        
    def wrap_pipeline(self, pipeline) -> None:
        """装饰器包裹 pipeline.run_stage"""
        original_run_stage = pipeline.run_stage
        
        async def wrapped_run_stage(stage_name: str, **kwargs) -> Any:
            # 发送阶段开始事件
            await self.event_bus.publish(PipelineEvent(
                event_type=EventType.STAGE_START,
                data={"stage": stage_name},
                timestamp=time.time()
            ))
            
            stage_start = time.time()
            result = await original_run_stage(stage_name, **kwargs)
            stage_end = time.time()
            
            # 记录阶段耗时
            self._stage_times[stage_name] = stage_end - stage_start
            
            # 发送阶段结束事件
            await self.event_bus.publish(PipelineEvent(
                event_type=EventType.STAGE_END,
                data={"stage": stage_name, "duration": stage_end - stage_start},
                timestamp=time.time()
            ))
            
            return result
        
        pipeline.run_stage = wrapped_run_stage
    
    def get_report(self) -> dict:
        """生成 performance.json"""
        return {
            "total_time": sum(self._stage_times.values()),
            "stages": self._stage_times,
            "chunks": self._chunk_times,
        }
```

### ChunkTracer

```python
# src/subtap/metrics/chunk_trace.py
from collections import deque

class ChunkTracer:
    def __init__(self, event_bus: EventBus, window_size: int = 10):
        self.event_bus = event_bus
        self._window_size = window_size
        self._chunks: list[dict] = []
        self._latency_window: deque[float] = deque(maxlen=window_size)
        
    def on_chunk_end(self, event: PipelineEvent) -> None:
        """记录 chunk 结束，使用滑动窗口计算平均值"""
        chunk_data = event.data
        latency = chunk_data["end_time"] - chunk_data["start_time"]
        
        # 添加到滑动窗口
        self._latency_window.append(latency)
        
        # 计算滑动窗口平均值
        avg_latency = sum(self._latency_window) / len(self._latency_window)
        
        # 记录 chunk
        self._chunks.append({
            "id": chunk_data["chunk_id"],
            "time": latency,
            "avg": avg_latency,
            "model": chunk_data.get("model", "unknown"),
        })
    
    def get_slow_chunks(self, threshold: float = 1.5) -> list[dict]:
        """获取 slow chunks"""
        if not self._latency_window:
            return []
        
        avg = sum(self._latency_window) / len(self._latency_window)
        return [
            chunk for chunk in self._chunks
            if chunk["time"] > avg * threshold
        ]
```

### SlowChunkDetector

```python
# src/subtap/metrics/slow_detector.py
class SlowChunkDetector:
    def __init__(self, threshold: float = 1.5):
        self.threshold = threshold
        self._slow_chunks: list[dict] = []
        
    def check(self, chunk_latency: float, avg_latency: float) -> bool:
        """检查是否为 slow chunk"""
        return chunk_latency > avg_latency * self.threshold
    
    def add_slow_chunk(self, chunk_id: int, latency: float, avg: float) -> None:
        """添加 slow chunk 记录"""
        self._slow_chunks.append({
            "id": chunk_id,
            "time": latency,
            "avg": avg,
            "threshold": self.threshold,
        })
    
    def get_slow_chunks(self) -> list[dict]:
        """获取所有 slow chunks"""
        return self._slow_chunks
```

### PipelineDashboard (Textual)

```python
# src/subtap/ui/dashboard.py
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, ProgressBar, Static
import asyncio

class PipelineDashboard(App):
    def __init__(self, event_bus: EventBus, profiler: PipelineProfiler):
        super().__init__()
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
        """启动事件处理"""
        self.run_worker(self.event_bus.start())
        
    async def _throttled_update(self, update_func) -> None:
        """节流更新，防止闪烁"""
        now = asyncio.get_event_loop().time()
        if now - self._last_update >= self._update_throttle:
            await update_func()
            self._last_update = now
```

### EventBridge

```python
# src/subtap/ui/event_bridge.py
class EventBridge:
    def __init__(self, event_bus: EventBus, dashboard: PipelineDashboard):
        self.event_bus = event_bus
        self.dashboard = dashboard
        
    def connect(self):
        """连接事件到 UI 更新"""
        self.event_bus.subscribe(EventType.STAGE_START, self._on_stage_start)
        self.event_bus.subscribe(EventType.CHUNK_END, self._on_chunk_end)
        self.event_bus.subscribe(EventType.PROGRESS, self._on_progress)
        
    async def _on_stage_start(self, event: PipelineEvent) -> None:
        """处理阶段开始事件"""
        await self.dashboard._throttled_update(
            lambda: self.dashboard.update_stage(event.data["stage"])
        )
        
    async def _on_chunk_end(self, event: PipelineEvent) -> None:
        """处理 chunk 结束事件"""
        await self.dashboard._throttled_update(
            lambda: self.dashboard.update_chunk(event.data)
        )
```

## 中文状态映射

```python
STAGE_CN = {
    "prepare": "音频标准化",
    "chunk": "音频切段",
    "asr": "语音识别",
    "clean": "文本优化",
    "segment": "智能断句",
    "align": "字幕对齐",
    "export": "字幕导出",
}
```

## 配置集成

```python
# src/subtap/schemas/config.py
class MetricsConfig(BaseModel):
    """性能分析配置"""
    enabled: bool = True
    slow_threshold: float = 1.5  # slow chunk 阈值
    output_path: str = "performance.json"
```

## 输出格式

```json
{
  "total_time": 12.4,
  "stages": {
    "asr": {"time": 5.2, "chunks": 14},
    "clean": {"time": 1.1},
    "segment": {"time": 0.6},
    "align": {"time": 3.8},
    "export": {"time": 0.4}
  },
  "chunks": [
    {"id": 0, "time": 0.3, "model": "qwen3-asr-0.6b"},
    {"id": 1, "time": 0.4, "model": "qwen3-asr-0.6b", "slow": true}
  ],
  "slow_chunks": [
    {"id": 1, "time": 0.4, "avg": 0.25, "threshold": 1.5}
  ],
  "bottleneck": "asr"
}
```

## 验收标准

1. ✔ TUI 实时显示 pipeline 状态
2. ✔ chunk 级进度可见
3. ✔ performance.json 生成
4. ✔ 中文状态完整
5. ✔ 无日志刷屏
6. ✔ pipeline 无侵入
7. ✔ UI 与 core 完全解耦
