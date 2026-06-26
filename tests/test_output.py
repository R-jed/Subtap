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


def test_lifecycle_init(tmp_path):
    """Test OutputLifecycle initialization."""
    from subtap.output.lifecycle import OutputLifecycle

    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)

    assert version_dir.exists()
    assert (version_dir / "artifacts").exists()


def test_lifecycle_write_user_artifact(tmp_path):
    """Test writing user artifact."""
    from subtap.output.lifecycle import OutputLifecycle

    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)

    output_path = lifecycle.write_user_artifact("test.srt", "content")
    assert output_path.exists()
    assert output_path.read_text() == "content"


def test_lifecycle_write_report(tmp_path):
    """Test writing report."""
    from subtap.output.lifecycle import OutputLifecycle

    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)

    output_path = lifecycle.write_report("# Report\n\nContent")
    assert output_path.exists()
    assert output_path.read_text() == "# Report\n\nContent"


def test_lifecycle_write_metrics(tmp_path):
    """Test writing metrics."""
    from subtap.output.lifecycle import OutputLifecycle

    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)

    metrics = {"total_duration": 24.8}
    output_path = lifecycle.write_metrics(metrics)
    assert output_path.exists()

    import json
    data = json.loads(output_path.read_text())
    assert data["total_duration"] == 24.8


def test_lifecycle_write_artifacts(tmp_path):
    """Test writing artifacts."""
    from subtap.output.lifecycle import OutputLifecycle

    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)

    artifacts = {
        "asr": {"segments": [1, 2, 3]},
        "segments": {"sentences": [1, 2]}
    }
    lifecycle.write_artifacts(artifacts)

    assert (version_dir / "artifacts" / "asr.json").exists()
    assert (version_dir / "artifacts" / "segments.json").exists()


def test_lifecycle_finalize(tmp_path):
    """Test finalizing output."""
    from subtap.output.lifecycle import OutputLifecycle

    version_dir = tmp_path / "v1"
    lifecycle = OutputLifecycle(version_dir)

    lifecycle.write_user_artifact("test.srt", "content")
    result = lifecycle.finalize_output()

    assert "files" in result
    assert "checksum" in result
