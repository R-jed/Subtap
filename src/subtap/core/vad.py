"""VAD-based silence splitting using Silero VAD or pydub fallback."""

from __future__ import annotations

import logging

import numpy as np
import torch
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk
from subtap.core.workspace import Workspace

logger = logging.getLogger(__name__)

# Sensitivity mapping: maps user-facing level to min_silence_duration_ms
_SENSITIVITY_MAP = {
    "low": 300,    # fewer, longer pauses detected
    "normal": 150, # balanced
    "high": 80,    # more, shorter pauses detected
}


def _load_silero_vad():
    """Load Silero VAD model (cached by silero_vad internally)."""
    from silero_vad import load_silero_vad
    return load_silero_vad()


def _get_speech_segments_silero(
    audio_path,
    threshold: float = 0.5,
    min_silence_ms: int = 150,
) -> list[list[float]]:
    """Get speech segments using Silero VAD.

    Returns list of [start_sec, end_sec] pairs.
    """
    from silero_vad import get_speech_timestamps

    audio = AudioSegment.from_file(audio_path)
    # Silero VAD requires 16kHz mono
    audio = audio.set_frame_rate(16000).set_channels(1)
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    # Normalize to [-1, 1] range (pydub samples are int16 range)
    samples = samples / 32768.0

    model = _load_silero_vad()
    speech_timestamps = get_speech_timestamps(
        torch.from_numpy(samples),
        model,
        threshold=threshold,
        sampling_rate=16000,
        min_silence_duration_ms=min_silence_ms,
        min_speech_duration_ms=250,
        speech_pad_ms=30,
        return_seconds=True,
    )

    # Convert [{"start": float, "end": float}, ...] to [[start, end], ...]
    return [[seg["start"], seg["end"]] for seg in speech_timestamps]


def split_chunks(workspace: Workspace, config: SubtapConfig) -> list[Chunk]:
    """Split source audio into chunks based on silence detection.

    Uses Silero VAD (preferred) or pydub detect_nonsilent fallback to find
    speech segments, then merges short segments and splits long ones.

    Returns list of Chunk models and writes chunks.jsonl to workspace.
    """
    vad_cfg = config.audio.vad
    audio = AudioSegment.from_file(workspace.source_audio)

    if vad_cfg.use_silero_vad:
        min_silence_ms = _SENSITIVITY_MAP.get(vad_cfg.sensitivity, 150)
        logger.info(
            "Using Silero VAD (sensitivity=%s, min_silence=%dms)",
            vad_cfg.sensitivity,
            min_silence_ms,
        )
        nonsilent = _get_speech_segments_silero(
            workspace.source_audio,
            threshold=0.5,
            min_silence_ms=min_silence_ms,
        )
        # Convert seconds to ms for uniform processing below
        nonsilent = [[s * 1000, e * 1000] for s, e in nonsilent]
    else:
        logger.info("Using pydub detect_nonsilent fallback")
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
