"""Phase 22: Model load/release lifecycle events.

Verifies that ASR and Align stages publish MODEL_LOAD_START, MODEL_LOAD_DONE,
MODEL_RELEASE_START, MODEL_RELEASE_DONE events through the EventBus.
"""

from __future__ import annotations

import pytest

from subtap.core.align import run_align
from subtap.core.asr import run_asr
from subtap.core.workspace import Workspace
from subtap.metrics.events import EventType, PipelineEvent
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import (
    AlignedSegment,
    ASRSegment,
    Chunk,
    SentenceSegment,
)


class _CollectingBus:
    """Non-async event collector for sync tests."""

    def __init__(self):
        self.events: list[PipelineEvent] = []

    def publish_nowait(self, event: PipelineEvent) -> None:
        self.events.append(event)


class _MockASR:
    name = "mlx-qwen-asr"

    def __init__(self):
        self._model = object()
        self.transcribe_called = False
        self._fail = False

    def transcribe(self, chunks, language=None, hotwords=None):
        self.transcribe_called = True
        if self._fail:
            raise RuntimeError("ASR inference failed")
        return [
            ASRSegment(
                chunk_id=c.chunk_id,
                segment_id=0,
                start_sec=c.start_sec,
                end_sec=c.end_sec,
                text="测试",
                confidence=0.9,
            )
            for c in chunks
        ]

    def release_model(self):
        self._model = None


class _MockAligner:
    name = "mlx-qwen-aligner"

    def __init__(self):
        self._model = object()
        self._fail = False

    def align(self, sentences, audio_path):
        if self._fail:
            raise RuntimeError("Align inference failed")
        return [
            AlignedSegment(
                sentence_id=s.sentence_id,
                start_sec=s.start_sec,
                end_sec=s.end_sec,
                text=s.text,
            )
            for s in sentences
        ]

    def release_model(self):
        self._model = None


def _setup_asr_workspace(tmp_path) -> Workspace:
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    chunk = Chunk(chunk_id=0, start_sec=0.0, end_sec=1.0, path="chunks/chunk.wav")
    workspace.chunks_jsonl.write_text(chunk.model_dump_json() + "\n", encoding="utf-8")
    (workspace.root / "chunks").mkdir(exist_ok=True)
    (workspace.root / "chunks" / "chunk.wav").write_bytes(b"fake")
    return workspace


def _setup_align_workspace(tmp_path) -> Workspace:
    config = SubtapConfig()
    workspace = Workspace(config, base_dir=tmp_path / "work")
    workspace.ensure_dirs()
    workspace.source_audio.write_bytes(b"fake")
    sentence = SentenceSegment(
        sentence_id=0,
        chunk_id=0,
        start_sec=0.0,
        end_sec=1.0,
        text="测试",
        source_text="测试",
    )
    workspace.sentences_jsonl.write_text(
        sentence.model_dump_json() + "\n", encoding="utf-8"
    )
    return workspace


# ── ASR events ───────────────────────────────────────────────────────────────


def test_asr_emits_model_load_and_release_events(monkeypatch, tmp_path):
    """run_asr should emit all 4 model lifecycle events."""
    workspace = _setup_asr_workspace(tmp_path)
    config = SubtapConfig()
    config.asr.model = "asr_0.6b"
    config.asr.quantization = "q8"

    bus = _CollectingBus()
    backend = _MockASR()
    monkeypatch.setattr("subtap.core.asr.get_backend", lambda *_a, **_k: backend)

    run_asr(workspace, config, event_bus=bus, task_id="test-task")

    types = [e.event_type for e in bus.events]
    assert EventType.MODEL_LOAD_START in types
    assert EventType.MODEL_LOAD_DONE in types
    assert EventType.MODEL_RELEASE_START in types
    assert EventType.MODEL_RELEASE_DONE in types


def test_asr_model_events_carry_correct_payload(monkeypatch, tmp_path):
    """ASR model events should include task_id, stage, model name."""
    workspace = _setup_asr_workspace(tmp_path)
    config = SubtapConfig()
    config.asr.model = "asr_1.7b"
    config.asr.quantization = "q4"

    bus = _CollectingBus()
    backend = _MockASR()
    monkeypatch.setattr("subtap.core.asr.get_backend", lambda *_a, **_k: backend)

    run_asr(workspace, config, event_bus=bus, task_id="payload-test")

    model_events = [
        e
        for e in bus.events
        if e.event_type
        in (
            EventType.MODEL_LOAD_START,
            EventType.MODEL_LOAD_DONE,
            EventType.MODEL_RELEASE_START,
            EventType.MODEL_RELEASE_DONE,
        )
    ]
    assert len(model_events) == 4
    for event in model_events:
        assert event.data["task_id"] == "payload-test"
        assert event.data["stage"] == "asr"
        assert event.data["model"] == "asr_1.7b-q4"


def test_asr_no_release_events_when_keep_model_alive(monkeypatch, tmp_path):
    """When keep_model_alive=True, no release events should be emitted."""
    workspace = _setup_asr_workspace(tmp_path)
    config = SubtapConfig()
    config.asr.keep_model_alive = True

    bus = _CollectingBus()
    backend = _MockASR()
    monkeypatch.setattr("subtap.core.asr.get_backend", lambda *_a, **_k: backend)

    run_asr(workspace, config, event_bus=bus, task_id="keep-alive-test")

    types = [e.event_type for e in bus.events]
    assert EventType.MODEL_LOAD_START in types
    assert EventType.MODEL_LOAD_DONE in types
    assert EventType.MODEL_RELEASE_START not in types
    assert EventType.MODEL_RELEASE_DONE not in types


def test_asr_release_events_emitted_on_transcribe_failure(monkeypatch, tmp_path):
    """Even when transcribe() raises, release events should fire (finally block)."""
    workspace = _setup_asr_workspace(tmp_path)
    config = SubtapConfig()

    bus = _CollectingBus()
    backend = _MockASR()
    backend._fail = True
    monkeypatch.setattr("subtap.core.asr.get_backend", lambda *_a, **_k: backend)

    with pytest.raises(RuntimeError, match="ASR inference failed"):
        run_asr(workspace, config, event_bus=bus, task_id="fail-test")

    types = [e.event_type for e in bus.events]
    assert EventType.MODEL_LOAD_START in types
    # MODEL_LOAD_DONE should NOT be in types because exception happens before it
    assert EventType.MODEL_LOAD_DONE not in types
    # Release events MUST fire even on failure
    assert EventType.MODEL_RELEASE_START in types
    assert EventType.MODEL_RELEASE_DONE in types


# ── Align events ─────────────────────────────────────────────────────────────


def test_align_emits_model_load_and_release_events(monkeypatch, tmp_path):
    """run_align should emit all 4 model lifecycle events."""
    workspace = _setup_align_workspace(tmp_path)
    config = SubtapConfig()

    bus = _CollectingBus()
    backend = _MockAligner()
    monkeypatch.setattr(
        "subtap.core.align.get_aligner_backend", lambda *_a, **_k: backend
    )

    run_align(workspace, config, event_bus=bus, task_id="align-test")

    types = [e.event_type for e in bus.events]
    assert EventType.MODEL_LOAD_START in types
    assert EventType.MODEL_LOAD_DONE in types
    assert EventType.MODEL_RELEASE_START in types
    assert EventType.MODEL_RELEASE_DONE in types


def test_align_model_events_carry_correct_payload(monkeypatch, tmp_path):
    """Align model events should include task_id, stage, model name."""
    workspace = _setup_align_workspace(tmp_path)
    config = SubtapConfig()
    config.align.model = "aligner"
    config.align.quantization = "q4"

    bus = _CollectingBus()
    backend = _MockAligner()
    monkeypatch.setattr(
        "subtap.core.align.get_aligner_backend", lambda *_a, **_k: backend
    )

    run_align(workspace, config, event_bus=bus, task_id="align-payload")

    model_events = [
        e
        for e in bus.events
        if e.event_type
        in (
            EventType.MODEL_LOAD_START,
            EventType.MODEL_LOAD_DONE,
            EventType.MODEL_RELEASE_START,
            EventType.MODEL_RELEASE_DONE,
        )
    ]
    assert len(model_events) == 4
    for event in model_events:
        assert event.data["task_id"] == "align-payload"
        assert event.data["stage"] == "align"
        assert event.data["model"] == "aligner-q4"


def test_align_no_release_events_when_keep_model_alive(monkeypatch, tmp_path):
    """When keep_model_alive=True, no release events should be emitted."""
    workspace = _setup_align_workspace(tmp_path)
    config = SubtapConfig()
    config.align.keep_model_alive = True

    bus = _CollectingBus()
    backend = _MockAligner()
    monkeypatch.setattr(
        "subtap.core.align.get_aligner_backend", lambda *_a, **_k: backend
    )

    run_align(workspace, config, event_bus=bus, task_id="align-keep-alive")

    types = [e.event_type for e in bus.events]
    assert EventType.MODEL_LOAD_START in types
    assert EventType.MODEL_LOAD_DONE in types
    assert EventType.MODEL_RELEASE_START not in types
    assert EventType.MODEL_RELEASE_DONE not in types


def test_align_release_events_emitted_on_align_failure(monkeypatch, tmp_path):
    """Even when align() raises, release events should fire (finally block)."""
    workspace = _setup_align_workspace(tmp_path)
    config = SubtapConfig()

    bus = _CollectingBus()
    backend = _MockAligner()
    backend._fail = True
    monkeypatch.setattr(
        "subtap.core.align.get_aligner_backend", lambda *_a, **_k: backend
    )

    with pytest.raises(RuntimeError, match="Align inference failed"):
        run_align(workspace, config, event_bus=bus, task_id="align-fail")

    types = [e.event_type for e in bus.events]
    assert EventType.MODEL_LOAD_START in types
    assert EventType.MODEL_LOAD_DONE not in types
    assert EventType.MODEL_RELEASE_START in types
    assert EventType.MODEL_RELEASE_DONE in types


def test_asr_no_events_when_no_event_bus(monkeypatch, tmp_path):
    """When event_bus=None, no events should be published (no crash)."""
    workspace = _setup_asr_workspace(tmp_path)
    config = SubtapConfig()

    backend = _MockASR()
    monkeypatch.setattr("subtap.core.asr.get_backend", lambda *_a, **_k: backend)

    result = run_asr(workspace, config, event_bus=None)
    assert result["segment_count"] == 1


def test_align_no_events_when_no_event_bus(monkeypatch, tmp_path):
    """When event_bus=None, align should not crash."""
    workspace = _setup_align_workspace(tmp_path)
    config = SubtapConfig()

    backend = _MockAligner()
    monkeypatch.setattr(
        "subtap.core.align.get_aligner_backend", lambda *_a, **_k: backend
    )

    result = run_align(workspace, config, event_bus=None)
    assert result["aligned_count"] == 1
