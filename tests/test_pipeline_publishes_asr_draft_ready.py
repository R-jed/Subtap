"""Phase 23: pipeline publishes ASR draft streaming events."""

from subtap.core.pipeline import Pipeline
from subtap.metrics.events import EventBus, EventType
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment, Chunk


class MockASRBackend:
    name = "mlx-qwen-asr"

    def __init__(self):
        self._model = object()
        self._progress_callback = None

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def transcribe(self, chunks, language=None, hotwords=None):
        segments = []
        for index, chunk in enumerate(chunks, start=1):
            segments.append(
                ASRSegment(
                    chunk_id=chunk.chunk_id,
                    segment_id=0,
                    start_sec=chunk.start_sec,
                    end_sec=chunk.end_sec,
                    text="测试字幕",
                    confidence=0.9,
                )
            )
            if self._progress_callback is not None:
                self._progress_callback(index, len(chunks), chunk)
        return segments

    def release_model(self):
        self._model = None


def _drain_events(bus: EventBus):
    events = []
    while not bus._queue.empty():
        events.append(bus._queue.get_nowait())
    return events


def test_pipeline_publishes_asr_draft_ready(monkeypatch, tmp_path):
    """ASR stage should publish one ASR_DRAFT_READY event per draft segment."""
    config = SubtapConfig()
    bus = EventBus()
    pipeline = Pipeline(config, tmp_path / "work", event_bus=bus, task_id="task-1")
    pipeline.workspace.ensure_dirs()

    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=1.0, path="chunks/chunk.wav")
    pipeline.workspace.chunks_jsonl.write_text(
        chunk.model_dump_json() + "\n",
        encoding="utf-8",
    )
    (pipeline.workspace.root / "chunks").mkdir(exist_ok=True)
    (pipeline.workspace.root / "chunks" / "chunk.wav").write_bytes(b"fake")

    monkeypatch.setattr(
        "subtap.core.asr.get_backend", lambda *_a, **_k: MockASRBackend()
    )

    pipeline.run_stage("asr")

    events = _drain_events(bus)
    asr_events = [
        event for event in events if event.event_type == EventType.ASR_DRAFT_READY
    ]
    assert len(asr_events) == 1
    assert asr_events[0].data["task_id"] == "task-1"
    assert asr_events[0].data["stage"] == "asr"
    assert asr_events[0].data["chunk_id"] == 0
    assert asr_events[0].data["text"] == "测试字幕"
    assert asr_events[0].data["item_index"] == 1
    assert asr_events[0].data["total_items"] == 1
    assert asr_events[0].data["message_zh"] == "已生成 ASR 草稿"
    progress_events = [
        event for event in events if event.event_type == EventType.PROGRESS
    ]
    assert len(progress_events) == 1
    assert progress_events[0].data["progress"] == 100
    assert progress_events[0].data["item_index"] == 1
    assert progress_events[0].data["message_zh"] == "已识别 1/1 个音频片段"
    assert events.index(progress_events[0]) < next(
        index
        for index, event in enumerate(events)
        if event.event_type == EventType.MODEL_RELEASE_START
    )
