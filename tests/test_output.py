"""Tests for output system."""

import pytest
from pathlib import Path
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


def test_versioning_first_version(tmp_path):
    """Test first version creation."""
    from subtap.output.versioning import VersionManager

    manager = VersionManager(tmp_path, "video")
    version = manager.next_version()
    assert version == 1


def test_versioning_increment(tmp_path):
    """Test version increment."""
    from subtap.output.versioning import VersionManager

    # Create v1
    (tmp_path / "video" / "v1").mkdir(parents=True)

    manager = VersionManager(tmp_path, "video")
    version = manager.next_version()
    assert version == 2


def test_versioning_create_latest_link(tmp_path):
    """Test latest symlink creation."""
    from subtap.output.versioning import VersionManager

    manager = VersionManager(tmp_path, "video")
    manager.create_latest_link(1)

    latest_link = tmp_path / "video" / "latest"
    assert latest_link.exists()
    assert latest_link.is_symlink()
    assert latest_link.readlink() == Path("v1")


def test_versioning_cleanup_old_versions(tmp_path):
    """Test old version cleanup."""
    from subtap.output.versioning import VersionManager

    # Create v1, v2, v3, v4, v5, v6
    for i in range(1, 7):
        (tmp_path / "video" / f"v{i}").mkdir(parents=True)

    manager = VersionManager(tmp_path, "video")
    manager.cleanup_old_versions(keep_last=3)

    # Should keep v4, v5, v6
    assert not (tmp_path / "video" / "v1").exists()
    assert not (tmp_path / "video" / "v2").exists()
    assert not (tmp_path / "video" / "v3").exists()
    assert (tmp_path / "video" / "v4").exists()
    assert (tmp_path / "video" / "v5").exists()
    assert (tmp_path / "video" / "v6").exists()


def test_output_engine_init(tmp_path):
    """Test OutputEngine initialization."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)

    assert engine.output_dir == tmp_path
    assert engine.input_name == "video"
    assert engine.version == 1


def test_output_engine_write_final(tmp_path):
    """Test writing final output."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)

    output_path = engine.write_final("srt", "1\n00:00:01,000 --> 00:00:02,000\nHello")
    assert output_path.exists()
    assert output_path.name == "video.srt"


def test_output_engine_write_report(tmp_path):
    """Test writing report."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)

    output_path = engine.write_report("# Report")
    assert output_path.exists()
    assert output_path.name == "video_report.md"


def test_output_engine_write_metrics(tmp_path):
    """Test writing metrics."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)

    metrics = {"total_duration": 24.8}
    output_path = engine.write_metrics(metrics)
    assert output_path.exists()
    assert output_path.name == "video_metrics.json"


def test_output_engine_finalize(tmp_path):
    """Test finalizing output."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)

    engine.write_final("srt", "content")
    result = engine.finalize_output()

    assert "files" in result
    assert "checksum" in result
    assert "version" in result
    assert result["version"] == 1

    # Check latest symlink
    latest_link = tmp_path / "video" / "latest"
    assert latest_link.exists()
    assert latest_link.is_symlink()


def test_tui_runner_with_output_engine(tmp_path):
    """Test TUIRunner with OutputEngine."""
    from subtap.ui.tui import TUIRunner
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)

    runner = TUIRunner(use_tui=False, output_engine=engine)
    assert runner.output_engine == engine


def test_tui_colors_defined():
    """Test TUI color styles are defined."""
    from subtap.ui.colors import (
        STAGE_TITLE, PROGRESS_BAR, PROGRESS_ACTIVE,
        ERROR, FILE_PATH, TIMING, SUCCESS, HEADER
    )

    from rich.style import Style

    assert isinstance(STAGE_TITLE, Style)
    assert isinstance(PROGRESS_BAR, Style)
    assert isinstance(ERROR, Style)


def test_cli_run_uses_output_engine(tmp_path):
    """Test CLI run command uses OutputEngine."""
    from typer.testing import CliRunner
    from subtap.cli import app

    runner = CliRunner()
    # This will be tested with mock in integration
    # For now, just verify the command exists
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    # Verify --timestamp option exists
    assert "--timestamp" in result.output or "--no-timestamp" in result.output


def test_output_config_has_timestamp():
    """Test OutputConfig has timestamp field."""
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    assert hasattr(config, 'timestamp')
    assert config.timestamp is True


def test_output_engine_with_timestamp(tmp_path):
    """Test OutputEngine works with timestamp config."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig(timestamp=True)
    engine = OutputEngine(tmp_path, "video.mp3", config)
    assert engine.config.timestamp is True


def test_full_output_flow(tmp_path):
    """Test complete output flow."""
    from subtap.output.engine import OutputEngine
    from subtap.schemas.config import OutputConfig

    config = OutputConfig()
    engine = OutputEngine(tmp_path, "video.mp3", config)

    # Write final output
    engine.write_final("srt", "1\n00:00:01,000 --> 00:00:02,000\nHello")

    # Write report
    engine.write_report("# Report\n\nQuality: 92/100")

    # Write metrics
    engine.write_metrics({"total_duration": 24.8})

    # Write artifacts
    engine.write_artifacts({
        "asr": {"segments": [1, 2, 3]},
        "segments": {"sentences": [1, 2]}
    })

    # Finalize
    result = engine.finalize_output()

    # Verify structure
    version_dir = tmp_path / "video" / "v1"
    assert version_dir.exists()
    assert (version_dir / "video.srt").exists()
    assert (version_dir / "video_report.md").exists()
    assert (version_dir / "video_metrics.json").exists()
    assert (version_dir / "artifacts" / "asr.json").exists()
    assert (version_dir / "artifacts" / "segments.json").exists()

    # Verify latest link
    latest_link = tmp_path / "video" / "latest"
    assert latest_link.exists()
    assert latest_link.is_symlink()

    # Verify result
    assert result["version"] == 1
    assert "checksum" in result
