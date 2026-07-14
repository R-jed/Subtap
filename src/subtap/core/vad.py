"""VAD-based silence splitting using bundled Silero VAD or pydub fallback."""

from __future__ import annotations

from importlib.resources import as_file, files
import logging

import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import sherpa_onnx

from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import Chunk
from subtap.core.workspace import Workspace

logger = logging.getLogger(__name__)


class VADError(Exception):
    """VAD processing error with user-facing context."""


# Sensitivity mapping: maps user-facing level to min_silence_duration_ms
_SENSITIVITY_MAP = {
    "low": 300,  # fewer, longer pauses detected
    "normal": 150,  # balanced
    "high": 80,  # more, shorter pauses detected
}

# Qwen3-ForcedAligner supports at most 180 seconds per input.
_FORCED_ALIGNER_MAX_SEC = 180.0
_LOW_ENERGY_SEARCH_SEC = 5.0


def _normalize_pcm(audio: AudioSegment) -> np.ndarray:
    """Convert signed PCM samples of any width to float32 in [-1, 1]."""
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    pcm_scale = float(1 << (8 * audio.sample_width - 1))
    return samples / pcm_scale


def _get_speech_segments_silero(
    audio: AudioSegment,
    threshold: float = 0.5,
    min_silence_ms: int = 150,
    min_speech_duration_ms: int = 250,
) -> list[list[float]]:
    """Get speech segments using the bundled Silero model through sherpa-onnx.

    Args:
        audio: Already-loaded AudioSegment to avoid double-loading.
        threshold: Speech detection threshold (0.0-1.0).
        min_silence_ms: Minimum silence duration to split on.
        min_speech_duration_ms: Minimum speech segment duration.

    Returns list of [start_sec, end_sec] pairs.

    Raises:
        VADError: If audio processing or VAD inference fails.
    """
    try:
        # Silero VAD requires 16kHz mono
        audio = audio.set_frame_rate(16000).set_channels(1)
        samples = _normalize_pcm(audio)
    except Exception as e:
        raise VADError(f"音频格式转换失败（需要 16kHz 单声道）: {e}") from e

    try:
        duration_sec = len(samples) / 16000.0
        # Exact model shipped by silero-vad 6.2.1; provenance is recorded in
        # resources/SILERO-VAD-MODEL.json. sherpa-onnx only replaces the runtime.
        model_resource = files("subtap").joinpath("resources", "silero_vad.onnx")
        with as_file(model_resource) as model_path:
            vad_config = sherpa_onnx.VadModelConfig()
            vad_config.silero_vad.model = str(model_path)
            vad_config.silero_vad.threshold = threshold
            vad_config.silero_vad.min_silence_duration = min_silence_ms / 1000.0
            vad_config.silero_vad.min_speech_duration = min_speech_duration_ms / 1000.0
            vad_config.silero_vad.max_speech_duration = duration_sec + 1.0
            vad_config.silero_vad.window_size = 512
            vad_config.sample_rate = 16000
            vad_config.num_threads = 1
            vad_config.provider = "cpu"

            detector = sherpa_onnx.VoiceActivityDetector(
                vad_config,
                buffer_size_in_seconds=duration_sec + 1.0,
            )
            for offset in range(0, len(samples), 512):
                detector.accept_waveform(samples[offset : offset + 512])
            detector.flush()

            speech_segments: list[list[float]] = []
            while not detector.empty():
                segment = detector.front
                speech_segments.append(
                    [
                        round(max(0.0, segment.start / 16000.0 - 0.03), 3),
                        round(
                            min(
                                duration_sec,
                                (segment.start + len(segment.samples)) / 16000.0 + 0.03,
                            ),
                            3,
                        ),
                    ]
                )
                detector.pop()
    except Exception as e:
        raise VADError(
            f"Silero VAD 推理失败: {e}\n"
            f"参数: threshold={threshold}, min_silence_ms={min_silence_ms}, "
            f"min_speech_duration_ms={min_speech_duration_ms}"
        ) from e

    return speech_segments


def split_chunks(workspace: Workspace, config: SubtapConfig) -> list[Chunk]:
    """Split source audio into chunks based on silence detection.

    Uses Silero VAD (preferred) or pydub detect_nonsilent fallback to find
    speech segments, then merges short segments and splits long ones.

    Returns list of Chunk models and writes chunks.jsonl to workspace.

    Raises:
        VADError: If audio loading or VAD processing fails.
    """
    vad_cfg = config.audio.vad
    min_silence_ms = _SENSITIVITY_MAP[vad_cfg.sensitivity]

    try:
        audio = AudioSegment.from_file(workspace.source_audio)
    except Exception as e:
        raise VADError(f"音频文件加载失败: {workspace.source_audio}\n错误: {e}") from e

    if vad_cfg.use_silero_vad:
        logger.info(
            "Using bundled Silero VAD via sherpa-onnx "
            "(sensitivity=%s, min_silence=%dms, threshold=%.2f)",
            vad_cfg.sensitivity,
            min_silence_ms,
            vad_cfg.silero_threshold,
        )
        nonsilent = _get_speech_segments_silero(
            audio,
            threshold=vad_cfg.silero_threshold,
            min_silence_ms=min_silence_ms,
            min_speech_duration_ms=vad_cfg.silero_min_speech_duration_ms,
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
        raise VADError("未检测到语音，请确认音频包含可识别人声或调整 VAD 灵敏度")

    # Merge nearby segments (gap < min_silence_sec)
    merged: list[list[float]] = []
    for start_ms, end_ms in nonsilent:
        if start_ms < 0 or end_ms <= start_ms or end_ms > len(audio):
            raise VADError(
                f"VAD 返回无效语音区间: {start_ms / 1000:.3f}s → {end_ms / 1000:.3f}s"
            )
        start_sec = start_ms / 1000.0
        end_sec = end_ms / 1000.0
        if merged and (start_sec - merged[-1][1]) < vad_cfg.min_silence_sec:
            merged[-1][1] = end_sec
        else:
            merged.append([start_sec, end_sec])

    # Preserve every detected utterance. The forced aligner accepts up to
    # 180 seconds; reuse mlx-audio's low-energy splitter only above that limit.
    final_segments: list[list[float]] = []
    for start, end in merged:
        if end - start <= _FORCED_ALIGNER_MAX_SEC:
            final_segments.append([start, end])
            continue

        from mlx_audio.stt.models.qwen3_asr.qwen3_asr import (
            split_audio_into_chunks,
        )

        region = audio[int(start * 1000) : int(end * 1000)]
        region = region.set_frame_rate(16000).set_channels(1)
        samples = _normalize_pcm(region)
        split_target_sec = _FORCED_ALIGNER_MAX_SEC - _LOW_ENERGY_SEARCH_SEC
        if split_target_sec <= 0:
            raise VADError("对齐器时长上限必须大于低能量边界搜索窗口")
        for chunk_samples, offset_sec in split_audio_into_chunks(
            samples,
            sr=16000,
            chunk_duration=split_target_sec,
            min_chunk_duration=0.0,
            search_expand_sec=_LOW_ENERGY_SEARCH_SEC,
        ):
            chunk_start = start + offset_sec
            chunk_end = min(
                end,
                chunk_start + len(chunk_samples) / 16000.0,
            )
            if chunk_end - chunk_start > _FORCED_ALIGNER_MAX_SEC + 1 / 16000:
                raise VADError("低能量切分结果超过 ForcedAligner 180 秒输入上限")
            final_segments.append([chunk_start, chunk_end])

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
