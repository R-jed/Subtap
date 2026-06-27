"""VAD-based silence splitting using pydub."""

from __future__ import annotations


from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk
from subtap.core.workspace import Workspace


def split_chunks(workspace: Workspace, config: SubtapConfig) -> list[Chunk]:
    """Split source audio into chunks based on silence detection.

    Uses pydub's detect_nonsilent to find speech segments, then
    merges short segments and splits long ones according to config.

    Returns list of Chunk models and writes chunks.jsonl to workspace.
    """
    vad_cfg = config.audio.vad
    audio = AudioSegment.from_wav(workspace.source_audio)

    # detect_nonsilent returns list of [start_ms, end_ms]
    nonsilent = detect_nonsilent(
        audio,
        min_silence_len=int(vad_cfg.min_silence_sec * 1000),
        silence_thresh=-40,  # dBFS
        seek_step=10,  # ms
    )

    if not nonsilent:
        # Whole file is speech (or whole file is silence)
        nonsilent = [[0, len(audio)]]

    # Merge nearby segments (gap < min_silence_sec)
    merged: list[list[float]] = []
    for start_ms, end_ms in nonsilent:
        start_sec = start_ms / 1000.0
        end_sec = end_ms / 1000.0
        if merged and (start_sec - merged[-1][1]) < vad_cfg.min_silence_sec:
            merged[-1][1] = end_sec
        else:
            merged.append([start_sec, end_sec])

    # Split oversized chunks and drop undersized ones
    final_segments: list[list[float]] = []
    for start, end in merged:
        dur = end - start
        if dur < vad_cfg.min_chunk_sec:
            continue
        # Split if longer than max_chunk_sec
        while dur > vad_cfg.max_chunk_sec:
            final_segments.append([start, start + vad_cfg.max_chunk_sec])
            start += vad_cfg.max_chunk_sec
            dur = end - start
        if dur >= vad_cfg.min_chunk_sec:
            final_segments.append([start, end])

    if not final_segments:
        # Fallback: treat whole file as one chunk
        final_segments = [[0.0, len(audio) / 1000.0]]

    # Export individual chunk WAVs and build Chunk list
    chunks: list[Chunk] = []
    workspace.chunks_dir.mkdir(parents=True, exist_ok=True)

    for i, (start, end) in enumerate(final_segments):
        start_ms = int(start * 1000)
        end_ms = int(end * 1000)
        segment = audio[start_ms:end_ms]
        chunk_path = workspace.chunk_path(i)
        segment.export(str(chunk_path), format="wav")
        chunks.append(
            Chunk(
                chunk_id=i,
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                path=str(chunk_path.relative_to(workspace.root)),
            )
        )

    # Write chunks.jsonl
    with open(workspace.chunks_jsonl, "w") as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + "\n")

    return chunks
