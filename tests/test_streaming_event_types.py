"""Phase 23: streaming event type contract."""

from subtap.metrics.events import EventType


def test_streaming_event_types_exist():
    """Streaming subtitle lifecycle events should be explicit."""
    assert EventType.AUDIO_CHUNK_READY.value == "audio_chunk_ready"
    assert EventType.ASR_DRAFT_READY.value == "asr_draft_ready"
    assert EventType.ENHANCEMENT_READY.value == "enhancement_ready"
    assert EventType.SENTENCE_CANDIDATE_READY.value == "sentence_candidate_ready"
    assert EventType.ALIGNMENT_READY.value == "alignment_ready"
    assert EventType.SUBTITLE_PREVIEW_READY.value == "subtitle_preview_ready"
    assert EventType.MODEL_LOAD_START.value == "model_load_start"
    assert EventType.MODEL_LOAD_DONE.value == "model_load_done"
    assert EventType.MODEL_RELEASE_START.value == "model_release_start"
    assert EventType.MODEL_RELEASE_DONE.value == "model_release_done"
    assert EventType.PIPELINE_PLAN.value == "pipeline_plan"
