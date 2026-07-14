"""Tests for batch interactive config wizard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


from subtap.batch_config import BatchConfig
from subtap.batch_interactive import (
    run_config_wizard,
    prompt_choice,
    prompt_int,
    prompt_bool,
    scan_directory,
    validate_files,
    confirm_files,
)


class TestPromptChoice:
    """Test prompt_choice function."""

    def test_default_selection(self):
        with patch("builtins.input", return_value=""):
            result = prompt_choice("Choose", ["a", "b", "c"], default="b")
            assert result == "b"

    def test_numeric_selection(self):
        with patch("builtins.input", return_value="2"):
            result = prompt_choice("Choose", ["a", "b", "c"], default="a")
            assert result == "b"

    def test_invalid_then_valid(self):
        with patch("builtins.input", side_effect=["invalid", "1"]):
            result = prompt_choice("Choose", ["a", "b", "c"], default="a")
            assert result == "a"


class TestPromptInt:
    """Test prompt_int function."""

    def test_default_value(self):
        with patch("builtins.input", return_value=""):
            result = prompt_int("Value", default=25, min_val=10, max_val=60)
            assert result == 25

    def test_custom_value(self):
        with patch("builtins.input", return_value="30"):
            result = prompt_int("Value", default=25, min_val=10, max_val=60)
            assert result == 30

    def test_out_of_range(self):
        with patch("builtins.input", side_effect=["100", "30"]):
            result = prompt_int("Value", default=25, min_val=10, max_val=60)
            assert result == 30


class TestPromptBool:
    """Test prompt_bool function."""

    def test_default_false(self):
        with patch("builtins.input", return_value=""):
            result = prompt_bool("Enable?", default=False)
            assert result is False

    def test_yes(self):
        with patch("builtins.input", return_value="y"):
            result = prompt_bool("Enable?", default=False)
            assert result is True

    def test_no(self):
        with patch("builtins.input", return_value="n"):
            result = prompt_bool("Enable?", default=True)
            assert result is False


class TestRunConfigWizard:
    """Test run_config_wizard function."""

    def test_wizard_creates_config(self, tmp_path):
        config_path = tmp_path / "batch-config.yaml"
        # Simulate user accepting all defaults
        with patch("builtins.input", return_value=""):
            config = run_config_wizard(config_path)
        assert isinstance(config, BatchConfig)
        assert config.mode == "fast"
        assert config_path.exists()

    def test_wizard_custom_values(self, tmp_path):
        config_path = tmp_path / "batch-config.yaml"
        # Simulate user selecting custom values
        inputs = [
            "2",  # mode: quality
            "3",  # enhance: api
            "2",  # translate_to: en
            "2",  # bilingual: source-first
            "",  # max_chars: default (25)
            "",  # min_chars: default (10)
            "y",  # punctuation: yes
            "2",  # subtitle_language: en
        ]
        with patch("builtins.input", side_effect=inputs):
            config = run_config_wizard(config_path)
        assert config.mode == "quality"
        assert config.enhance == "api"
        assert config.translate_to == "en"
        assert config.bilingual == "source-first"
        assert config.punctuation is True
        assert config.subtitle_language == "en"


class TestFileSelection:
    """Test file selection functions."""

    def test_scan_directory(self, tmp_path):
        """Test scanning directory for media files."""
        # Create test files
        (tmp_path / "video1.mp4").touch()
        (tmp_path / "audio1.wav").touch()
        (tmp_path / "audio2.mp3").touch()
        (tmp_path / "text.txt").touch()  # Should be ignored

        files = scan_directory(tmp_path)
        assert len(files) == 3
        assert all(f.suffix in (".mp4", ".wav", ".mp3") for f in files)

    def test_validate_files(self, tmp_path):
        """Test file validation."""
        # Create existing and non-existing files
        existing = tmp_path / "exists.mp4"
        existing.touch()
        missing = tmp_path / "missing.mp4"

        valid, invalid = validate_files([existing, missing])
        assert len(valid) == 1
        assert len(invalid) == 1
        assert valid[0] == existing
        assert invalid[0] == missing

    def test_confirm_files(self):
        """Test file confirmation prompt."""
        files = [Path("a.mp4"), Path("b.wav"), Path("c.mp3")]

        # User confirms
        with patch("builtins.input", return_value="y"):
            assert confirm_files(files) is True

        # User declines
        with patch("builtins.input", return_value="n"):
            assert confirm_files(files) is False
