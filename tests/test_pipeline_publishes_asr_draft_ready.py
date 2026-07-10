"""Phase 23: pipeline publishes ASR draft streaming events."""

from subtap.core.pipeline import Pipeline
from subtap.metrics.events import EventBus, EventType
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import ASRSegment, Chunk


class MockASRBackend:
    name = "mlx-qwen-asr"

    def __init__(self):
        self._model = object()

    def transcribe(self, chunks, language=None, hotwords=None):
        return [
            ASRSegment(
                chunk_id=chunk.chunk_id,
                segment_id=0,
                start_sec=chunk.start_sec,
                end_sec=chunk.end_sec,
                text="测试字幕",
                confidence=0.9,
            )
            for chunk in chunks
        ]

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
    assert asr_events[0].data["message_zh"] == "已生成 ASR 草稿"
