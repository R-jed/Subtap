"""Phase 24: report performance summary."""

from pathlib import Path

from subtap.core.report import generate_report
from subtap.metrics.performance import build_subtitle_performance_metrics


def test_report_performance_summary_is_chinese_and_explains_privacy():
    """report.md should explain RTF, timing, LLM, privacy, and model residency."""
    metrics = build_subtitle_performance_metrics(
        timings={"asr": 3.0, "align": 2.0, "clean": 1.0, "segment": 0.2, "export": 0.1},
        audio_duration_sec=10.0,
        chunks_total=4,
        subtitles_total=8,
        alignment_enabled=True,
        asr_model="asr_0.6b",
        aligner_model="aligner",
        quantization="q8",
        enhance_mode="api",
    )

    report = generate_report(
        quality_score=90,
        error_count=0,
        fixable_count=0,
        fixed_count=0,
        segment_count=8,
        timings={"asr": 3.0},
        mode="fast",
        input_file=Path("input.wav"),
        output_format="srt",
        performance_metrics=metrics,
    )

    assert "RTF" in report
    assert "RTF = 总处理耗时 / 音频时长" in report
    assert "音频是否发送外部：否" in report
    assert "文本是否发送外部：是" in report
    assert "任务结束后不会常驻模型" in report
