import pytest
from subtap.schemas.config import VADConfig


def test_vad_config_silero_field():
    """VADConfig should have use_silero_vad field with default True."""
    config = VADConfig()
    assert hasattr(config, 'use_silero_vad')
    assert config.use_silero_vad is True


def test_vad_config_silero_false():
    """VADConfig should accept use_silero_vad=False."""
    config = VADConfig(use_silero_vad=False)
    assert config.use_silero_vad is False
