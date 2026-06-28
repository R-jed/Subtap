"""Phase 25: deterministic manual review sample picker."""

from subtap.quality.sample_picker import pick_manual_review_segments


def test_quality_sample_picker_uses_real_quality_signals_not_random():
    """Samples should come from confidence, slow chunks, timing, and CPS signals."""
    subtitles = [
        {
            "subtitle_id": 1,
            "start_sec": 0.0,
            "end_sec": 1.0,
            "text": "低置信",
            "alignment_confidence": 0.4,
        },
        {
            "subtitle_id": 2,
            "start_sec": 2.0,
            "end_sec": 2.1,
            "text": "这是一条非常非常非常非常非常长的字幕",
            "alignment_confidence": 0.9,
        },
        {
            "subtitle_id": 3,
            "start_sec": 5.0,
            "end_sec": 4.0,
            "text": "时间轴异常",
            "alignment_confidence": 0.9,
        },
    ]

    samples = pick_manual_review_segments(
        subtitles, slow_chunks=[{"subtitle_id": 2, "rtf": 3.0}]
    )
    reasons = {sample["reason"] for sample in samples}

    assert "低置信片段" in reasons
    assert "慢速片段" in reasons
    assert "时间轴异常片段" in reasons
    assert "CPS 过高片段" in reasons
