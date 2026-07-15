"""Subtitle performance metrics contract."""

from __future__ import annotations

import json

import pytest

from subtap.metrics.performance import (
    build_subtitle_performance_metrics,
    load_pipeline_measurements,
)
from subtap.schemas.config import SubtapConfig


def test_metrics_subtitle_performance_fields_complete():
    """metrics.json payload should expose subtitle-engine performance fields."""
    metrics = build_subtitle_performance_metrics(
        timings={
            "asr": 3.0,
            "align": 2.0,
            "clean": 1.0,
            "segment": 0.2,
            "export": 0.1,
        },
        total_runtime_sec=8.0,
        audio_duration_sec=10.0,
        chunks_total=4,
        subtitles_total=8,
        alignment_enabled=True,
        asr_model="asr_0.6b",
        aligner_model="aligner",
        quantization="q8",
        enhance_mode="local",
        asr_model_load_time_sec=0.4,
        aligner_model_load_time_sec=0.5,
        keep_model_alive=True,
        slow_chunks=[{"chunk_id": 1, "rtf": 2.1}],
    )

    for field in (
        "audio_duration_sec",
        "metrics_schema_version",
        "total_runtime_sec",
        "rtf",
        "asr_model_load_time_sec",
        "asr_runtime_sec",
        "aligner_model_load_time_sec",
        "align_runtime_sec",
        "alignment_enabled",
        "enhancement_runtime_sec",
        "segmentation_runtime_sec",
        "export_runtime_sec",
        "chunks_total",
        "slow_chunks",
        "chunk_timing_available",
        "subtitles_total",
        "asr_model",
        "aligner_model",
        "quantization",
        "device_backend",
        "keep_model_alive",
        "warmup",
        "external_text_sent",
        "external_audio_sent",
        "estimated_llm_cost",
    ):
        assert field in metrics

    assert metrics["total_runtime_sec"] == 8.0
    assert metrics["metrics_schema_version"] == 2
    assert metrics["rtf"] == 0.8
    assert metrics["device_backend"] == "mlx-metal"
    assert metrics["keep_model_alive"] is True
    assert metrics["warmup"] is False
    assert metrics["chunk_timing_available"] is True


def test_load_pipeline_measurements_reads_real_runtime_and_events(tmp_path):
    media_info = tmp_path / "media_info.json"
    run_meta = tmp_path / "run_meta.json"
    event_log = tmp_path / "run.log.jsonl"
    media_info.write_text(json.dumps({"duration": 10.0}), encoding="utf-8")
    run_meta.write_text(json.dumps({"total_time_sec": 8.0}), encoding="utf-8")
    events = [
        {
            "event_type": "model_load_done",
            "timestamp": 1.0,
            "data": {"stage": "asr", "duration_sec": 0.4},
        },
        {
            "event_type": "model_load_done",
            "timestamp": 2.0,
            "data": {"stage": "align", "duration_sec": 0.5},
        },
    ]
    event_log.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    measurements = load_pipeline_measurements(media_info, run_meta, event_log)

    assert measurements == {
        "audio_duration_sec": 10.0,
        "total_runtime_sec": 8.0,
        "asr_model_load_time_sec": 0.4,
        "aligner_model_load_time_sec": 0.5,
    }


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("media_info.json", {"duration": 0}),
        ("media_info.json", {"duration": "unknown"}),
        ("run_meta.json", {"total_time_sec": 0}),
    ],
)
def test_load_pipeline_measurements_rejects_invalid_required_values(
    tmp_path, filename, payload
):
    media_info = tmp_path / "media_info.json"
    run_meta = tmp_path / "run_meta.json"
    event_log = tmp_path / "run.log.jsonl"
    media_info.write_text(json.dumps({"duration": 10.0}), encoding="utf-8")
    run_meta.write_text(json.dumps({"total_time_sec": 8.0}), encoding="utf-8")
    (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")
    event_log.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        load_pipeline_measurements(media_info, run_meta, event_log)


def test_load_pipeline_measurements_rejects_corrupt_event_log(tmp_path):
    media_info = tmp_path / "media_info.json"
    run_meta = tmp_path / "run_meta.json"
    event_log = tmp_path / "run.log.jsonl"
    media_info.write_text(json.dumps({"duration": 10.0}), encoding="utf-8")
    run_meta.write_text(json.dumps({"total_time_sec": 8.0}), encoding="utf-8")
    event_log.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="run.log.jsonl:1"):
        load_pipeline_measurements(media_info, run_meta, event_log)


def test_load_pipeline_measurements_rejects_missing_model_measurements(tmp_path):
    media_info = tmp_path / "media_info.json"
    run_meta = tmp_path / "run_meta.json"
    event_log = tmp_path / "run.log.jsonl"
    media_info.write_text(json.dumps({"duration": 10.0}), encoding="utf-8")
    run_meta.write_text(json.dumps({"total_time_sec": 8.0}), encoding="utf-8")
    event_log.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="align, asr"):
        load_pipeline_measurements(media_info, run_meta, event_log)


def test_generate_metrics_uses_verified_run_artifacts_and_config(tmp_path):
    from subtap.cli.pipeline_cli import _generate_metrics

    work_dir = tmp_path / "work"
    output_dir = tmp_path / "output"
    work_dir.mkdir()
    (work_dir / "chunks").mkdir()
    (work_dir / "chunks" / "chunks.jsonl").write_text(
        json.dumps({"chunk_id": 0}) + "\n", encoding="utf-8"
    )
    (work_dir / "aligned.jsonl").write_text(
        json.dumps({"sentence_id": 0}) + "\n", encoding="utf-8"
    )
    (work_dir / "media_info.json").write_text(
        json.dumps({"duration": 10.0}), encoding="utf-8"
    )
    (work_dir / "run_meta.json").write_text(
        json.dumps({"total_time_sec": 8.0}), encoding="utf-8"
    )
    event_log = work_dir / "run.log.jsonl"
    event_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "model_load_done",
                        "data": {"stage": "asr", "duration_sec": 0.4},
                    }
                ),
                json.dumps(
                    {
                        "event_type": "model_load_done",
                        "data": {"stage": "align", "duration_sec": 0.5},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = SubtapConfig()
    config.asr.keep_model_alive = True

    _generate_metrics(
        config,
        {"asr": 3.0, "align": 2.0},
        work_dir,
        output_dir,
        "local",
        event_log,
    )

    metrics = json.loads((work_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["total_runtime_sec"] == 8.0
    assert metrics["rtf"] == 0.8
    assert metrics["asr_model_load_time_sec"] == 0.4
    assert metrics["aligner_model_load_time_sec"] == 0.5
    assert metrics["keep_model_alive"] is True
    assert metrics["chunk_timing_available"] is False


def test_metrics_jsonl_count_rejects_missing_or_corrupt_records(tmp_path):
    from subtap.cli.pipeline_cli import _count_jsonl

    with pytest.raises(FileNotFoundError):
        _count_jsonl(tmp_path / "missing.jsonl")

    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text('{"valid": true}\nnot-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt.jsonl:2"):
        _count_jsonl(corrupt)
