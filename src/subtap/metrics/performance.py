"""Subtitle performance metrics helpers."""

from __future__ import annotations

from typing import Any


def calculate_rtf(total_runtime_sec: float, audio_duration_sec: float) -> float:
    """Calculate real-time factor: total runtime divided by audio duration."""
    if audio_duration_sec <= 0:
        return 0.0
    return round(total_runtime_sec / audio_duration_sec, 2)


def build_subtitle_performance_metrics(
    *,
    timings: dict[str, float],
    audio_duration_sec: float,
    chunks_total: int,
    subtitles_total: int,
    alignment_enabled: bool,
    asr_model: str,
    aligner_model: str,
    quantization: str,
    enhance_mode: str,
    slow_chunks: list[dict[str, Any]] | None = None,
    estimated_llm_cost: float = 0.0,
) -> dict[str, Any]:
    """Build the metrics.json payload for subtitle-engine observability."""
    total_runtime_sec = round(sum(timings.values()), 2)
    align_runtime_sec = round(timings.get("align", 0.0), 2) if alignment_enabled else 0
    return {
        "audio_duration_sec": round(audio_duration_sec, 2),
        "total_runtime_sec": total_runtime_sec,
        "rtf": calculate_rtf(total_runtime_sec, audio_duration_sec),
        "asr_model_load_time_sec": round(timings.get("asr_model_load", 0.0), 2),
        "asr_runtime_sec": round(timings.get("asr", 0.0), 2),
        "aligner_model_load_time_sec": round(timings.get("aligner_model_load", 0.0), 2),
        "align_runtime_sec": align_runtime_sec,
        "alignment_enabled": alignment_enabled,
        "enhancement_runtime_sec": round(timings.get("clean", 0.0), 2),
        "segmentation_runtime_sec": round(timings.get("segment", 0.0), 2),
        "export_runtime_sec": round(timings.get("export", 0.0), 2),
        "chunks_total": chunks_total,
        "slow_chunks": slow_chunks or [],
        "subtitles_total": subtitles_total,
        "asr_model": asr_model,
        "aligner_model": aligner_model,
        "quantization": quantization,
        "device_backend": "mlx-metal",
        "keep_model_alive": False,
        "warmup": False,
        "external_text_sent": enhance_mode == "api",
        "external_audio_sent": False,
        "estimated_llm_cost": estimated_llm_cost,
    }
