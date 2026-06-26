"""Tests for setup business logic."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

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
