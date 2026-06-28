"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from subtap.schemas.config import SubtapConfig, VADConfig, AudioConfig, WorkspaceConfig


def pytest_configure(config):
    """Configure asyncio mode for all async tests."""
    config._inicache["asyncio_mode"] = "auto"


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """Create a synthetic WAV file with speech-like segments and silence."""
    # 0.5s tone, 0.6s silence, 0.5s tone (should produce 2+ chunks)
    tone1 = Sine(440).to_audio_segment(duration=500)
    silence = AudioSegment.silent(duration=600)
    tone2 = Sine(880).to_audio_segment(duration=500)

    audio = tone1 + silence + tone2
    audio = audio.set_frame_rate(16000).set_channels(1)

    wav_path = tmp_path / "test.wav"
    audio.export(str(wav_path), format="wav")
    return wav_path


@pytest.fixture
def test_config(tmp_path: Path) -> SubtapConfig:
    """Config pointing to a temporary workspace."""
    return SubtapConfig(
        audio=AudioConfig(
            sample_rate=16000,
            channels=1,
            format="wav",
            vad=VADConfig(
                min_silence_sec=0.4,
                min_chunk_sec=0.1,  # low threshold for short test audio
                max_chunk_sec=30.0,
            ),
        ),
        workspace=WorkspaceConfig(
            root=str(tmp_path / "work"),
            keep_intermediate=True,
        ),
    )
