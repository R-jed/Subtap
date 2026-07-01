"""Intelligent VAD-based silence splitting."""

from __future__ import annotations

import numpy as np
from pydub import AudioSegment

from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk
from subtap.core.workspace import Workspace
from subtap.core.vad_utils import (
    calculate_frame_energy,
    calculate_zero_crossing_rate,
    calculate_spectral_centroid,
    calculate_vad_probability,
    get_thresholds_for_sensitivity,
)


def split_chunks(workspace: Workspace, config: SubtapConfig) -> list[Chunk]:
    """Split source audio into chunks using intelligent VAD.

    Uses multi-feature fusion (energy + ZCR + spectral centroid)
    with adaptive thresholds based on sensitivity setting.

    Returns list of Chunk models and writes chunks.jsonl to workspace.
    """
    vad_cfg = config.audio.vad
    audio = AudioSegment.from_wav(workspace.source_audio)

    # Calculate multi-feature probabilities
    energy = calculate_frame_energy(audio, frame_duration_ms=30)
    zcr = calculate_zero_crossing_rate(audio, frame_duration_ms=30)
    spectral = calculate_spectral_centroid(audio, frame_duration_ms=30)

    # Combine features into VAD probability
    probability = calculate_vad_probability(energy, zcr, spectral)

    # Get thresholds based on sensitivity
    enter_threshold, exit_threshold = get_thresholds_for_sensitivity(vad_cfg.sensitivity)

    # Detect speech segments using hysteresis
    frame_duration_sec = 30 / 1000  # 30ms
    nonsilent = _detect_speech_segments_with_hysteresis(
        probability,
        enter_threshold,
        exit_threshold,
        frame_duration_sec,
    )

    if not nonsilent:
        # Whole file is speech (or whole file is silence)
        nonsilent = [[0, len(audio) / 1000.0]]

    # Merge nearby segments (gap < min_silence_sec)
    merged: list[list[float]] = []
    for start_sec, end_sec in nonsilent:
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


def _detect_speech_segments_with_hysteresis(
    probability: np.ndarray,
    enter_threshold: float,
    exit_threshold: float,
    frame_duration_sec: float,
) -> list[list[float]]:
    """Detect speech segments using hysteresis thresholding.

    Args:
        probability: Array of speech probabilities
        enter_threshold: Threshold to enter speech state
        exit_threshold: Threshold to exit speech state
        frame_duration_sec: Duration of each frame in seconds

    Returns:
        List of [start_sec, end_sec] pairs
    """
    segments = []
    in_speech = False
    start_sec = 0.0

    for i, prob in enumerate(probability):
        current_sec = i * frame_duration_sec

        if not in_speech:
            # Enter speech state when probability exceeds enter threshold
            if prob >= enter_threshold:
                in_speech = True
                start_sec = current_sec
        else:
            # Exit speech state when probability falls below exit threshold
            if prob < exit_threshold:
                in_speech = False
                end_sec = current_sec
                segments.append([start_sec, end_sec])

    # Handle case where speech continues to end of file
    if in_speech:
        end_sec = len(probability) * frame_duration_sec
        segments.append([start_sec, end_sec])

    return segments
