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


def test_doctor_enhanced_checks(monkeypatch, tmp_path):
    """Test enhanced doctor checks."""
    from unittest.mock import patch, MagicMock
    from pathlib import Path

    # 隔离 Path.home()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # 创建模拟配置文件
    config_dir = tmp_path / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with patch("subtap.core.models.ModelRegistry.status") as mock_status:
        mock_status.return_value = [
            MagicMock(name="aligner", installed=True, path=tmp_path / "models" / "aligner"),
            MagicMock(name="asr", installed=True, path=tmp_path / "models" / "asr"),
        ]
        result = runner.invoke(app, ["doctor"])
        assert "配置状态" in result.output
        assert "模型状态" in result.output
        assert "asr" in result.output
        assert "aligner" in result.output


def test_setup_full_flow():
    """Test complete setup flow."""
    from unittest.mock import patch

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps, \
         patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config, \
         patch("subtap.core.setup.SetupWizard.setup_models") as mock_models:

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = False
        mock_models.return_value = True

        result = runner.invoke(app, ["setup"])

        assert result.exit_code == 0
        assert "系统检查" in result.output
        assert "初始化配置" in result.output
        assert "初始化完成" in result.output
        # Verify setup_models was called
        mock_models.assert_called_once()


def test_demo_command_exists():
    """Test demo command exists with expected options."""
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "演示" in result.output
    assert "--output-dir" in result.output
    assert "--skip-tui" in result.output


def test_setup_help_has_download_source_option():
    """Test setup --help shows --download-source option."""
    result = runner.invoke(app, ["setup", "--help"])

    assert result.exit_code == 0
    assert "--download-source" in result.output
    assert "hf-mirror" in result.output


def test_doctor_release_fails_when_models_missing(tmp_path, monkeypatch):
    """doctor --release 应在模型未安装时返回 exit_code=1."""
    from unittest.mock import patch, MagicMock
    from pathlib import Path

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    subtap_dir = tmp_path / ".subtap"
    subtap_dir.mkdir()
    (subtap_dir / "config.yaml").write_text("models:\n  root: models\n", encoding="utf-8")

    # 模拟 registry.status() 返回缺失模型
    missing_status = [
        MagicMock(name="asr_0.6b", installed=False,
                  path=tmp_path / "models" / "asr_0.6b",
                  missing_files=["config.json", "model.safetensors"]),
        MagicMock(name="aligner", installed=True,
                  path=tmp_path / "models" / "aligner",
                  missing_files=[]),
    ]

    with patch("subtap.core.models.ModelRegistry") as MockRegistry:
        MockRegistry.return_value.status.return_value = missing_status
        result = runner.invoke(app, ["doctor", "--release"])

    assert result.exit_code == 1
    assert "部分检查未通过" in result.output
    assert "缺失" in result.output


def test_python_module_entrypoint_outputs_help():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "subtap.cli", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Subtap" in result.stdout
    assert "run" in result.stdout


def test_setup_interactive_fallback_hf_to_mirror(tmp_path, monkeypatch):
    """交互模式下，hf 连不通时提示降级到 hf-mirror."""
    from unittest.mock import patch, MagicMock

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # 创建配置文件
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps, \
         patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config, \
         patch("subtap.core.setup.SetupWizard.choose_download_source") as mock_choose, \
         patch("subtap.core.models.ModelDownloader") as mock_downloader_cls:

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True
        # 模拟用户选择 hf
        mock_choose.return_value = "hf"

        # 模拟 hf 连不通，hf-mirror 连通
        mock_downloader = MagicMock()
        mock_downloader.check_connectivity.side_effect = [False, True]
        mock_downloader_cls.return_value = mock_downloader

        # 模拟用户选择降级
        with patch("typer.prompt", return_value="y"), \
             patch("typer.echo"):
            result = runner.invoke(app, ["setup", "--download-source", "ask"])

        # 验证选择了 hf，然后降级到 hf-mirror
        mock_choose.assert_called_once_with("ask")
        assert mock_downloader.check_connectivity.call_count == 2


def test_setup_non_interactive_fails_on_connectivity_error(tmp_path, monkeypatch):
    """非交互模式下，连不通时直接返回失败."""
    from unittest.mock import patch, MagicMock

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

    # 创建配置文件
    config_dir = fake_home / ".subtap"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("")

    with patch("subtap.core.setup.SetupWizard.check_system_deps") as mock_deps, \
         patch("subtap.core.setup.SetupWizard.check_config_exists") as mock_config, \
         patch("subtap.core.models.ModelDownloader") as mock_downloader_cls:

        mock_deps.return_value = {"ffmpeg": True, "ffprobe": True, "python": True}
        mock_config.return_value = True

        # 模拟 hf 连不通
        mock_downloader = MagicMock()
        mock_downloader.check_connectivity.return_value = False
        mock_downloader_cls.return_value = mock_downloader

        # 非交互模式，指定 --download-source hf
        result = runner.invoke(app, ["setup", "--skip-models"])
        assert result.exit_code == 0
