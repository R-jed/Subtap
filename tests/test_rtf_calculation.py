"""Phase 24: RTF calculation."""

from subtap.metrics.performance import calculate_rtf


def test_rtf_is_total_runtime_divided_by_audio_duration():
    """RTF should be total runtime / audio duration."""
    assert calculate_rtf(total_runtime_sec=25.0, audio_duration_sec=10.0) == 2.5


def test_rtf_zero_when_audio_duration_missing():
    """Invalid audio duration should not raise or divide by zero."""
    assert calculate_rtf(total_runtime_sec=25.0, audio_duration_sec=0.0) == 0.0
