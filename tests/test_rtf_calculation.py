"""Phase 24: RTF calculation."""

import pytest

from subtap.metrics.performance import calculate_rtf


def test_rtf_is_total_runtime_divided_by_audio_duration():
    """RTF should be total runtime / audio duration."""
    assert calculate_rtf(total_runtime_sec=25.0, audio_duration_sec=10.0) == 2.5


def test_rtf_preserves_release_threshold_precision():
    assert calculate_rtf(total_runtime_sec=25.49, audio_duration_sec=100.0) == 0.2549


def test_rtf_zero_duration_is_invalid():
    """A zero duration means the source measurement is corrupt."""
    with pytest.raises(ValueError, match="audio_duration_sec"):
        calculate_rtf(total_runtime_sec=25.0, audio_duration_sec=0.0)
