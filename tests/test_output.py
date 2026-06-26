"""Tests for output system."""

import pytest
from subtap.output.exceptions import OutputError


def test_output_error_is_exception():
    """Test OutputError is a proper exception."""
    error = OutputError("test error")
    assert isinstance(error, Exception)
    assert str(error) == "test error"


def test_naming_strategy_final_name():
    """Test NamingStrategy generates correct final name."""
    from subtap.output.naming import NamingStrategy

    strategy = NamingStrategy("video.mp3")
    assert strategy.get_final_name("srt") == "video.srt"
    assert strategy.get_final_name("ass") == "video.ass"


def test_naming_strategy_report_name():
    """Test NamingStrategy generates correct report name."""
    from subtap.output.naming import NamingStrategy

    strategy = NamingStrategy("video.mp3")
    assert strategy.get_report_name() == "video_report.md"


def test_naming_strategy_metrics_name():
    """Test NamingStrategy generates correct metrics name."""
    from subtap.output.naming import NamingStrategy

    strategy = NamingStrategy("video.mp3")
    assert strategy.get_metrics_name() == "video_metrics.json"


def test_naming_strategy_artifact_name():
    """Test NamingStrategy generates correct artifact name."""
    from subtap.output.naming import NamingStrategy

    strategy = NamingStrategy("video.mp3")
    assert strategy.get_artifact_name("asr") == "video_asr.json"
