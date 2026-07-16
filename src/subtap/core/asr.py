"""ASR pipeline stage: load chunks → transcribe → write asr.jsonl."""

from __future__ import annotations

from pathlib import Path
import time

from subtap.backends.asr import get_backend
from subtap.core.models import _get_model_root
from subtap.metrics.events import EventBus, EventType, make_pipeline_event
from subtap.schemas.asr import ASRDraft
from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk, ASRSegment
from subtap.core.workspace import Workspace


def load_chunks(chunks_jsonl: Path) -> list[Chunk]:
    """Load chunks from JSONL file."""
    chunks: list[Chunk] = []
    with open(chunks_jsonl) as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(Chunk.model_validate_json(line))
    return chunks


def write_asr_segments(segments: list[ASRSegment], output_path: Path) -> None:
    """Write ASR segments to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for seg in segments:
            f.write(seg.model_dump_json() + "\n")


def write_asr_drafts(
    segments: list[ASRSegment],
    output_path: Path,
    model: str,
    quantization: str,
    event_bus: EventBus | None = None,
    task_id: str = "local",
) -> None:
    """Write ASRDraft reference-timing artifact."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(segments) or 1
    with open(output_path, "w") as f:
        for index, seg in enumerate(segments, start=1):
            draft = ASRDraft(
                chunk_id=seg.chunk_id,
                text=seg.text,
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
                confidence=seg.confidence,
                provider="qwen3_mlx",
                model=f"{model}-{quantization}",
            )
            f.write(draft.model_dump_json() + "\n")
            if event_bus is not None:
                event_bus.publish_nowait(
                    make_pipeline_event(
                        EventType.ASR_DRAFT_READY,
                        task_id=task_id,
                        stage="asr",
                        chunk_id=seg.chunk_id,
                        segment_id=seg.segment_id,
                        progress=round(index / total * 100),
                        duration_sec=seg.end_sec - seg.start_sec,
                        model=f"{model}-{quantization}",
                        text=seg.text,
                        item_index=index,
                        total_items=total,
                        message_zh="已生成 ASR 草稿",
                    )
                )


def _load_hotwords_from_glossary(
    lang: str = "zh", glossary_path: str | None = None
) -> list[str]:
    """Load correct hotword forms from glossary file for system_prompt injection."""
    from subtap.glossary.hotword import load_glossary
    from subtap.core.user_resources import default_glossary_path
    from pathlib import Path

    path = Path(glossary_path) if glossary_path else default_glossary_path()
    if glossary_path and not path.is_file():
        raise FileNotFoundError(f"热词表不存在：{path}")
    if not glossary_path and not path.exists():
        return []
    glossary = load_glossary(path, lang)
    return [hw.word for hw in glossary.hotwords]


def run_asr(
    workspace: Workspace,
    config: SubtapConfig,
    backend_name: str | None = None,
    event_bus: EventBus | None = None,
    task_id: str = "local",
) -> dict:
    """Run ASR stage: load chunks, transcribe, write asr.jsonl.

    Args:
        workspace: Workspace instance with paths.
        config: Subtap config (used for ASR backend settings).
        backend_name: Override backend name (defaults to config).

    Returns:
        Dict with segment_count.
    """
    # Load chunks
    chunks = load_chunks(workspace.chunks_jsonl)
    if not chunks:
        raise ValueError(f"No chunks found in {workspace.chunks_jsonl}")

    # Resolve backend
    asr_config = config.asr.model_copy()
    if backend_name:
        asr_config.backend = backend_name

    # Load hotwords: merge glossary file + config hotwords
    glossary_hotwords = _load_hotwords_from_glossary(
        glossary_path=config.clean.glossary_path
    )
    all_hotwords = list(set(glossary_hotwords + (asr_config.hotwords or [])))

    if asr_config.backend == "http-asr":
        backend = get_backend(asr_config, config.remote_api)
    else:
        backend = get_backend(asr_config, model_root=_get_model_root(config))

    # Resolve chunk paths to absolute
    abs_chunks: list[Chunk] = []
    for chunk in chunks:
        chunk_path = Path(chunk.path)
        if not chunk_path.is_absolute():
            chunk_path = workspace.root / chunk_path
        abs_chunks.append(chunk.model_copy(update={"path": str(chunk_path)}))

    # Transcribe
    model_name = f"{asr_config.model}-{asr_config.quantization}"
    if event_bus is not None:
        event_bus.publish_nowait(
            make_pipeline_event(
                EventType.MODEL_LOAD_START,
                task_id=task_id,
                stage="asr",
                model=model_name,
                message_zh="开始加载 ASR 模型",
            )
        )
    try:
        model_load_started = time.monotonic()
        load_model = getattr(backend, "load_model", None)
        if callable(load_model):
            load_model()
        model_load_time_sec = time.monotonic() - model_load_started
        if event_bus is not None:
            event_bus.publish_nowait(
                make_pipeline_event(
                    EventType.MODEL_LOAD_DONE,
                    task_id=task_id,
                    stage="asr",
                    duration_sec=model_load_time_sec,
                    model=model_name,
                    message_zh="ASR 模型加载完成",
                )
            )
        segments = backend.transcribe(
            abs_chunks,
            language=None,
            hotwords=all_hotwords or None,
        )
    finally:
        if not asr_config.keep_model_alive and hasattr(backend, "release_model"):
            if event_bus is not None:
                event_bus.publish_nowait(
                    make_pipeline_event(
                        EventType.MODEL_RELEASE_START,
                        task_id=task_id,
                        stage="asr",
                        model=model_name,
                        message_zh="开始释放 ASR 模型",
                    )
                )
            backend.release_model()
            if event_bus is not None:
                event_bus.publish_nowait(
                    make_pipeline_event(
                        EventType.MODEL_RELEASE_DONE,
                        task_id=task_id,
                        stage="asr",
                        model=model_name,
                        message_zh="ASR 模型已释放",
                    )
                )

    # Merge consecutive single-letter words (e.g. "U","F","S" → "UFS")
    for seg in segments:
        if hasattr(seg, "words") and seg.words:
            seg.words = _merge_single_letters(seg.words)

    # Write asr.jsonl
    write_asr_segments(segments, workspace.asr_jsonl)
    write_asr_drafts(
        segments,
        workspace.asr_draft_jsonl,
        model=asr_config.model,
        quantization=asr_config.quantization,
        event_bus=event_bus,
        task_id=task_id,
    )

    return {"segment_count": len(segments)}


def _merge_single_letters(words: list[dict]) -> list[dict]:
    """Merge consecutive single-character words into one word.

    ASR sometimes splits acronyms like "UFS" into ["U", "F", "S"].
    This function merges them back while preserving timestamps.
    Merges all single-character words (both ASCII and CJK) when they are temporally adjacent.
    """
    if not words:
        return words

    result = []
    buffer = ""
    buffer_start = 0.0
    buffer_end = 0.0

    for w in words:
        word_text = w["word"]
        if len(word_text) == 1:
            # Check if temporally adjacent to buffer
            if buffer and abs(w["start_sec"] - buffer_end) < 0.05:
                # Adjacent, continue buffering
                buffer += word_text
                buffer_end = w["end_sec"]
            else:
                # Not adjacent, flush buffer and start new
                if buffer:
                    result.append(
                        {
                            "word": buffer,
                            "start_sec": buffer_start,
                            "end_sec": buffer_end,
                        }
                    )
                buffer = word_text
                buffer_start = w["start_sec"]
                buffer_end = w["end_sec"]
        else:
            if buffer:
                result.append(
                    {
                        "word": buffer,
                        "start_sec": buffer_start,
                        "end_sec": buffer_end,
                    }
                )
                buffer = ""
            result.append(w)

    if buffer:
        result.append(
            {
                "word": buffer,
                "start_sec": buffer_start,
                "end_sec": buffer_end,
            }
        )

    return result
