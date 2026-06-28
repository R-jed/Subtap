"""Align pipeline stage: sentences.jsonl → forced alignment → aligned.jsonl."""

from __future__ import annotations

from pathlib import Path

from subtap.backends.align import get_aligner_backend
from subtap.metrics.events import EventBus, EventType, make_pipeline_event
from subtap.schemas.alignment import AlignedSubtitle, AlignedWord
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import SentenceSegment, AlignedSegment
from subtap.core.workspace import Workspace


def load_sentences(sentences_jsonl: Path) -> list[SentenceSegment]:
    """Load SentenceSegments from JSONL."""
    segments: list[SentenceSegment] = []
    with open(sentences_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(SentenceSegment.model_validate_json(line))
    return segments


def write_aligned(segments: list[AlignedSegment], output_path: Path) -> None:
    """Write AlignedSegments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in segments:
            f.write(seg.model_dump_json() + "\n")


def write_aligned_subtitles(
    segments: list[AlignedSegment],
    output_path: Path,
    event_bus: EventBus | None = None,
    task_id: str = "local",
    model: str = "aligner",
) -> None:
    """Write AlignedSubtitle final-timing artifact."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(segments) or 1
    with open(output_path, "w") as f:
        for index, seg in enumerate(segments, start=1):
            # Passthrough word-level timing from aligner
            words = (
                [
                    AlignedWord(
                        word=w["word"],
                        start_sec=w["start_sec"],
                        end_sec=w["end_sec"],
                    )
                    for w in seg.words
                ]
                if seg.words
                else []
            )
            subtitle = AlignedSubtitle(
                subtitle_id=seg.sentence_id,
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
                text=seg.text,
                words=words,
            )
            f.write(subtitle.model_dump_json() + "\n")
            if event_bus is not None:
                event_bus.publish_nowait(
                    make_pipeline_event(
                        EventType.ALIGNMENT_READY,
                        task_id=task_id,
                        stage="align",
                        subtitle_id=seg.sentence_id,
                        progress=round(index / total * 100),
                        duration_sec=seg.end_sec - seg.start_sec,
                        model=model,
                        message_zh="已完成字幕精对齐",
                    )
                )


def run_align(
    workspace: Workspace,
    config: SubtapConfig,
    backend_name: str | None = None,
    event_bus: EventBus | None = None,
    task_id: str = "local",
) -> dict:
    """Run align stage: load sentences → forced alignment → aligned.jsonl.

    Args:
        workspace: Workspace instance with paths.
        config: Subtap config.
        backend_name: Override aligner backend name.

    Returns:
        Dict with aligned_count.
    """
    # Load sentences
    sentences = load_sentences(workspace.sentences_jsonl)
    if not sentences:
        raise ValueError(f"No sentences found in {workspace.sentences_jsonl}")

    # Resolve backend
    align_config = config.align.model_copy()
    if backend_name:
        align_config.backend = backend_name

    backend = get_aligner_backend(align_config)

    # Align
    model_name = f"{align_config.model}-{align_config.quantization}"
    if event_bus is not None:
        event_bus.publish_nowait(
            make_pipeline_event(
                EventType.MODEL_LOAD_START,
                task_id=task_id,
                stage="align",
                model=model_name,
                message_zh="开始加载对齐模型",
            )
        )
    try:
        aligned = backend.align(sentences, workspace.source_audio)
        if event_bus is not None:
            event_bus.publish_nowait(
                make_pipeline_event(
                    EventType.MODEL_LOAD_DONE,
                    task_id=task_id,
                    stage="align",
                    model=model_name,
                    message_zh="对齐模型加载完成",
                )
            )
    finally:
        if not align_config.keep_model_alive and hasattr(backend, "release_model"):
            if event_bus is not None:
                event_bus.publish_nowait(
                    make_pipeline_event(
                        EventType.MODEL_RELEASE_START,
                        task_id=task_id,
                        stage="align",
                        model=model_name,
                        message_zh="开始释放对齐模型",
                    )
                )
            backend.release_model()
            if event_bus is not None:
                event_bus.publish_nowait(
                    make_pipeline_event(
                        EventType.MODEL_RELEASE_DONE,
                        task_id=task_id,
                        stage="align",
                        model=model_name,
                        message_zh="对齐模型已释放",
                    )
                )

    # Fix word timestamp quality for all aligners
    for seg in aligned:
        words = seg.words
        for k in range(len(words) - 1):
            # Step 1: fix zero/negative duration
            if words[k]["end_sec"] <= words[k]["start_sec"]:
                words[k]["end_sec"] = words[k]["start_sec"] + 0.020
            # Step 2: fix monotonicity (may cascade)
            if words[k]["end_sec"] > words[k + 1]["start_sec"]:
                words[k + 1]["start_sec"] = words[k]["end_sec"]

    # Write aligned.jsonl
    write_aligned(aligned, workspace.aligned_jsonl)
    write_aligned_subtitles(
        aligned,
        workspace.aligned_subtitles_jsonl,
        event_bus=event_bus,
        task_id=task_id,
        model=model_name,
    )

    return {"aligned_count": len(aligned)}
