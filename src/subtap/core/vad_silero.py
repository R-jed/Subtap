"""Silero VAD-based voice activity detection."""

from __future__ import annotations

import torch
import torchaudio
from pathlib import Path

from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk
from subtap.core.workspace import Workspace


def load_silero_vad():
    """Load Silero VAD model using silero-vad package."""
    from silero_vad import load_silero_vad as _load
    model = _load(onnx=False)
    return model


def detect_speech_segments(
    audio_path: Path,
    model,
    threshold: float = 0.5,
    min_silence_sec: float = 0.4,
) -> list[list[float]]:
    """Detect speech segments using Silero VAD.

    Args:
        audio_path: Path to audio file.
        model: Silero VAD model.
        threshold: Speech probability threshold.
        min_silence_sec: Minimum silence duration to split.

    Returns:
        List of [start_sec, end_sec] pairs.
    """
    from silero_vad import get_speech_timestamps, read_audio

    # Read audio
    wav = read_audio(str(audio_path), sampling_rate=16000)

    # Get speech timestamps
    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        threshold=threshold,
        min_silence_duration_ms=int(min_silence_sec * 1000),
        return_seconds=True,
    )

    # Convert to list of [start, end] pairs
    segments = []
    for ts in speech_timestamps:
        segments.append([ts['start'], ts['end']])

    return segments


def split_chunks_silero(
    workspace: Workspace,
    config: SubtapConfig,
    threshold: float = 0.5,
) -> list[Chunk]:
    """Split source audio into chunks using Silero VAD.

    Args:
        workspace: Workspace instance.
        config: Subtap config.
        threshold: Speech probability threshold (0.0-1.0).

    Returns:
        List of Chunk models and writes chunks.jsonl to workspace.
    """
    vad_cfg = config.audio.vad

    # Load Silero VAD model
    model = load_silero_vad()

    # Detect speech segments
    speech_segments = detect_speech_segments(
        workspace.source_audio,
        model,
        threshold=threshold,
        min_silence_sec=vad_cfg.min_silence_sec,
    )

    if not speech_segments:
        # Fallback: treat whole file as one chunk
        import torchaudio
        waveform, sample_rate = torchaudio.load(str(workspace.source_audio))
        duration = waveform.shape[1] / sample_rate
        speech_segments = [[0.0, duration]]

    # Split oversized chunks and drop undersized ones
    final_segments: list[list[float]] = []
    for start, end in speech_segments:
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
        import torchaudio
        waveform, sample_rate = torchaudio.load(str(workspace.source_audio))
        duration = waveform.shape[1] / sample_rate
        final_segments = [[0.0, duration]]

    # Export individual chunk WAVs and build Chunk list
    from pydub import AudioSegment
    audio = AudioSegment.from_wav(workspace.source_audio)

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
