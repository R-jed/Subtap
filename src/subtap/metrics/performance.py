"""Subtitle performance metrics helpers."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def calculate_rtf(total_runtime_sec: float, audio_duration_sec: float) -> float:
    """Calculate real-time factor: total runtime divided by audio duration."""
    if audio_duration_sec <= 0:
        raise ValueError("audio_duration_sec must be greater than zero")
    if total_runtime_sec < 0:
        raise ValueError("total_runtime_sec cannot be negative")
    return round(total_runtime_sec / audio_duration_sec, 6)


def _read_positive_json_number(path: Path, key: str) -> float:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: {key} must be a number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{path}: {key} must be greater than zero")
    return number


def load_pipeline_measurements(
    media_info_path: Path,
    run_meta_path: Path,
    event_log_path: Path,
) -> dict[str, float]:
    """Load verified runtime measurements produced by one pipeline run."""
    measurements = {
        "audio_duration_sec": _read_positive_json_number(media_info_path, "duration"),
        "total_runtime_sec": _read_positive_json_number(
            run_meta_path, "total_time_sec"
        ),
    }
    model_load_times = {"asr": 0.0, "align": 0.0}
    observed_stages: set[str] = set()
    for line_number, line in enumerate(
        event_log_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {event_log_path}:{line_number}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"{event_log_path}:{line_number} must be a JSON object")
        if event.get("event_type") != "model_load_done":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"{event_log_path}:{line_number} has invalid event data")
        stage = data.get("stage")
        if stage not in model_load_times:
            continue
        duration = data.get("duration_sec")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or float(duration) < 0
        ):
            raise ValueError(
                f"{event_log_path}:{line_number} has invalid model load duration"
            )
        model_load_times[stage] += float(duration)
        observed_stages.add(stage)

    missing = sorted(model_load_times.keys() - observed_stages)
    if missing:
        raise ValueError(
            f"{event_log_path} is missing model load measurements for: "
            + ", ".join(missing)
        )
    measurements.update(
        {
            "asr_model_load_time_sec": model_load_times["asr"],
            "aligner_model_load_time_sec": model_load_times["align"],
        }
    )
    return measurements


def build_subtitle_performance_metrics(
    *,
    timings: dict[str, float],
    total_runtime_sec: float,
    audio_duration_sec: float,
    chunks_total: int,
    subtitles_total: int,
    alignment_enabled: bool,
    asr_model: str,
    aligner_model: str,
    quantization: str,
    enhance_mode: str,
    asr_model_load_time_sec: float,
    aligner_model_load_time_sec: float,
    keep_model_alive: bool,
    slow_chunks: list[dict[str, Any]] | None = None,
    estimated_llm_cost: float = 0.0,
) -> dict[str, Any]:
    """Build the metrics.json payload for subtitle-engine observability."""
    if total_runtime_sec <= 0 or not math.isfinite(total_runtime_sec):
        raise ValueError("total_runtime_sec must be greater than zero")
    align_runtime_sec = round(timings.get("align", 0.0), 6) if alignment_enabled else 0
    return {
        "metrics_schema_version": 2,
        "audio_duration_sec": round(audio_duration_sec, 6),
        "total_runtime_sec": round(total_runtime_sec, 6),
        "rtf": calculate_rtf(total_runtime_sec, audio_duration_sec),
        "asr_model_load_time_sec": round(asr_model_load_time_sec, 6),
        "asr_runtime_sec": round(timings.get("asr", 0.0), 6),
        "aligner_model_load_time_sec": round(aligner_model_load_time_sec, 6),
        "align_runtime_sec": align_runtime_sec,
        "alignment_enabled": alignment_enabled,
        "enhancement_runtime_sec": round(timings.get("clean", 0.0), 6),
        "segmentation_runtime_sec": round(timings.get("segment", 0.0), 6),
        "export_runtime_sec": round(timings.get("export", 0.0), 6),
        "chunks_total": chunks_total,
        "slow_chunks": slow_chunks or [],
        "chunk_timing_available": slow_chunks is not None,
        "subtitles_total": subtitles_total,
        "asr_model": asr_model,
        "aligner_model": aligner_model,
        "quantization": quantization,
        "device_backend": "mlx-metal",
        "keep_model_alive": keep_model_alive,
        "warmup": False,
        "external_text_sent": enhance_mode == "api",
        "external_audio_sent": False,
        "estimated_llm_cost": estimated_llm_cost,
    }
