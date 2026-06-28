"""Phase 24: subtitle performance metrics fields."""

from subtap.metrics.performance import build_subtitle_performance_metrics


def test_metrics_subtitle_performance_fields_complete():
    """metrics.json payload should expose subtitle-engine performance fields."""
    metrics = build_subtitle_performance_metrics(
        timings={
            "asr_model_load": 0.4,
            "asr": 3.0,
            "aligner_model_load": 0.5,
            "align": 2.0,
            "clean": 1.0,
            "segment": 0.2,
            "export": 0.1,
        },
        audio_duration_sec=10.0,
        chunks_total=4,
        subtitles_total=8,
        alignment_enabled=True,
        asr_model="asr_0.6b",
        aligner_model="aligner",
        quantization="q8",
        enhance_mode="local",
        slow_chunks=[{"chunk_id": 1, "rtf": 2.1}],
    )

    for field in (
        "audio_duration_sec",
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

    assert metrics["rtf"] == 0.72
    assert metrics["device_backend"] == "mlx-metal"
    assert metrics["keep_model_alive"] is False
    assert metrics["warmup"] is False
