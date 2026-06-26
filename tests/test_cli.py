"""Tests for CLI commands."""

from __future__ import annotations

from typer.testing import CliRunner

from subtap.cli import app

runner = CliRunner()


def test_version():
    """subtap version should print version string."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "subtap" in result.output
    assert "0.1.0" in result.output


def test_init(tmp_path, monkeypatch):
    """subtap init should create ~/.subtap/ structure."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    subtap_dir = fake_home / ".subtap"
    assert subtap_dir.exists()
    assert (subtap_dir / "config.yaml").exists()
    assert (subtap_dir / "glossary" / "global.yaml").exists()
    assert (subtap_dir / "subtap.db").exists()


def test_doctor(tmp_path, monkeypatch):
    """subtap doctor should run without crashing."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # Create a minimal config so doctor can load it
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("audio:\n  sample_rate: 16000\n")

    result = runner.invoke(app, ["doctor"])
    # Should either pass (exit 0) or fail due to missing ffmpeg (exit 1)
    assert result.exit_code in (0, 1)
    assert "ffmpeg" in result.output.lower() or "python" in result.output.lower()


def test_doctor_workspace(tmp_path, monkeypatch):
    """subtap doctor --workspace should show workspace state."""
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("audio:\n  sample_rate: 16000\n")

    # Create a mock workspace
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    result = runner.invoke(app, ["doctor", "--workspace"])
    assert result.exit_code == 0
    assert "工作区" in result.output or "workspace" in result.output.lower()


def test_run_has_no_git_check_flag():
    """subtap run should accept --no-git-check flag."""
    # Just verify the flag is accepted (will fail on missing input file, that's ok)
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--no-git-check" in result.output


def test_run_has_no_cleanroom_flag():
    """subtap run should accept --no-cleanroom flag."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--no-cleanroom" in result.output


def test_quality_command_exists():
    """subtap quality command should exist."""
    result = runner.invoke(app, ["quality", "--help"])
    assert result.exit_code == 0
    assert "aligned.jsonl" in result.output
    assert "--fix" in result.output
    assert "--report-only" in result.output


def test_run_has_mode_flag():
    """subtap run should accept --mode flag."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--mode" in result.output


def test_run_mode_fast():
    """subtap run should accept --mode fast."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "fast" in result.output


def test_run_mode_quality():
    """subtap run should accept --mode quality."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "quality" in result.output


def test_run_mode_hybrid():
    """subtap run should accept --mode hybrid."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "hybrid" in result.output


def test_analyze_command_exists():
    """subtap analyze command should exist."""
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "SRT" in result.output or "srt" in result.output


def test_setup_command_exists():
    """Test that setup command exists."""
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    assert "初始化向导" in result.output


def test_setup_system_check():
    """Test setup system check step."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_check:
        mock_check.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert "系统检查" in result.output


def test_setup_system_check_failure():
    """Test setup system check when deps are missing."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_check:
        mock_check.return_value = {"ffmpeg": False, "ffprobe": True, "python": True}
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert result.exit_code == 1
        assert "系统检查未通过" in result.output


def test_setup_skip_models():
    """Test setup with --skip-models flag."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps, \
         patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config:
        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert result.exit_code == 0
        assert "模型安装（已跳过）" in result.output


def test_doctor_enhanced_checks():
    """Test enhanced doctor checks."""
    from unittest.mock import patch, MagicMock
    from pathlib import Path

    with patch("subtap.core.models.ModelRegistry.status") as mock_status:
        mock_status.return_value = [
            MagicMock(name="aligner", installed=True, path=Path("/tmp/aligner")),
            MagicMock(name="asr", installed=True, path=Path("/tmp/asr")),
        ]
        result = runner.invoke(app, ["doctor"])
        assert "模型状态" in result.output
        assert "配置状态" in result.output
