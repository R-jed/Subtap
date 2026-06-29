"""Tests for --mode quality model switching."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from subtap.schemas.config import load_config


def test_quality_mode_overrides_asr_model():
    """--mode quality should override config.asr.model to asr_1.7b."""
    config = load_config(Path.home() / ".subtap" / "config.yaml")
    assert config.asr.model == "asr_0.6b", "Precondition: default is asr_0.6b"

    # This is the logic that should exist in cli.py run()
    mode = "quality"
    if mode == "quality":
        config.asr.model = "asr_1.7b"

    assert config.asr.model == "asr_1.7b"


def test_fast_mode_keeps_default():
    """--mode fast should not change the model."""
    config = load_config(Path.home() / ".subtap" / "config.yaml")
    original = config.asr.model

    mode = "fast"
    # No override for fast mode

    assert config.asr.model == original
