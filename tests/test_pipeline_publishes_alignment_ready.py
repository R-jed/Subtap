"""Phase 23: pipeline publishes alignment streaming events."""

from pathlib import Path

from subtap.core.pipeline import Pipeline
from subtap.metrics.events import EventBus, EventType
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import AlignedSegment, SentenceSegment


class MockAlignerBackend:
    name = "mlx-qwen-aligner"

    def __init__(self):
        self._model = object()

    def align(self, sentences, audio_path: Path):
        return [
            AlignedSegment(
                sentence_id=sentence.sentence_id,
                start_sec=sentence.start_sec,
                end_sec=sentence.end_sec,
                text=sentence.text,
            )
            for sentence in sentences
        ]

    def release_model(self):
        self._model = None


def _drain_events(bus: EventBus):
    events = []
    while not bus._queue.empty():
        events.append(bus._queue.get_nowait())
    return events


def test_pipeline_publishes_alignment_ready(monkeypatch, tmp_path):
    """Align stage should publish one ALIGNMENT_READY event per aligned subtitle."""
    config = SubtapConfig()
    bus = EventBus()
    pipeline = Pipeline(config, tmp_path / "work", event_bus=bus, task_id="task-1")
    pipeline.workspace.ensure_dirs()
    pipeline.workspace.source_audio.write_bytes(b"fake")
    sentence = SentenceSegment(
        sentence_id=0,
        chunk_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="测试字幕",
        source_text="测试字幕",
    )
    pipeline.workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "subtap.core.align.get_aligner_backend",
        lambda *_a, **_k: MockAlignerBackend(),
    )

    pipeline.run_stage("align")

    events = _drain_events(bus)
    align_events = [
        event for event in events if event.event_type == EventType.ALIGNMENT_READY
    ]
    assert len(align_events) == 1
    assert align_events[0].data["task_id"] == "task-1"
    assert align_events[0].data["stage"] == "align"
    assert align_events[0].data["subtitle_id"] == 0
    assert align_events[0].data["message_zh"] == "已完成字幕精对齐"
