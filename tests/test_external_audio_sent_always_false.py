"""Phase 24: external audio privacy contract."""

from subtap.metrics.performance import build_subtitle_performance_metrics


def test_external_audio_sent_always_false_even_with_api_enhancement():
    """LLM API enhancement may send text, but never audio."""
    metrics = build_subtitle_performance_metrics(
        timings={"asr": 1.0},
        total_runtime_sec=1.0,
        audio_duration_sec=1.0,
        chunks_total=1,
        subtitles_total=1,
        alignment_enabled=True,
        asr_model="asr_0.6b",
        aligner_model="aligner",
        quantization="q8",
        enhance_mode="api",
        asr_model_load_time_sec=0.0,
        aligner_model_load_time_sec=0.0,
        keep_model_alive=False,
    )

    assert metrics["external_text_sent"] is True
    assert metrics["external_audio_sent"] is False
