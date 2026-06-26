"""Tests for setup business logic."""

import pytest
from pathlib import Path
from unittest.mock import patch

from subtap.core.setup import SetupWizard


def test_setup_wizard_init():
    """Test SetupWizard initialization."""
    wizard = SetupWizard()
    assert wizard is not None


def test_check_system_deps_ffmpeg_missing():
    """Test system check when ffmpeg is missing."""
    wizard = SetupWizard()
    with patch("shutil.which", return_value=None):
        result = wizard.check_system_deps()
        assert result["ffmpeg"] is False


def test_check_system_deps_ffmpeg_present():
    """Test system check when ffmpeg is present."""
    wizard = SetupWizard()
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        result = wizard.check_system_deps()
        assert result["ffmpeg"] is True


def test_check_system_deps_python_version():
    """Test Python version check."""
    wizard = SetupWizard()
    result = wizard.check_system_deps()
    assert "python" in result
    assert isinstance(result["python"], bool)


def test_check_config_exists_true(tmp_path):
    """Test config check when config exists."""
    wizard = SetupWizard()
    config_path = tmp_path / ".subtap" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("test: true")

    with patch("subtap.core.setup.Path.home", return_value=tmp_path):
        result = wizard.check_config_exists()
        assert result is True


def test_check_config_exists_false(tmp_path):
    """Test config check when config doesn't exist."""
    wizard = SetupWizard()

    with patch("subtap.core.setup.Path.home", return_value=tmp_path):
        result = wizard.check_config_exists()
        assert result is False


def test_run_init_success():
    """Test successful init."""
    wizard = SetupWizard()

    with patch("subtap.cli.init") as mock_init:
        mock_init.return_value = None
        result = wizard.run_init()
        assert result is True
        mock_init.assert_called_once()


def test_run_init_failure():
    """Test failed init."""
    wizard = SetupWizard()

    with patch("subtap.cli.init", side_effect=Exception("Init failed")):
        result = wizard.run_init()
        assert result is False
