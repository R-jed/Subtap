"""Tests for media processing module."""

from __future__ import annotations

import json
from pathlib import Path

from subtap.core.media import prepare_media
from subtap.core.workspace import Workspace
from subtap.schemas.config import SubtapConfig


def test_prepare_media_creates_wav(
    sample_wav: Path, test_config: SubtapConfig, tmp_path: Path
):
    """prepare_media should produce source.wav and media_info.json."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()

    media_info = prepare_media(sample_wav, ws, test_config)
    assert media_info.duration > 0

    # WAV file exists
    assert ws.source_audio.exists(), f"source.wav not found at {ws.source_audio}"
    assert ws.source_audio.stat().st_size > 0

    # media_info.json exists and is valid
    assert ws.media_info_path.exists()
    data = json.loads(ws.media_info_path.read_text())
    assert "duration" in data
    assert data["duration"] > 0
    assert data["sample_rate"] == 16000
    assert data["channels"] == 1


def test_media_info_model(sample_wav: Path, test_config: SubtapConfig, tmp_path: Path):
    """MediaInfo returned by prepare_media has correct fields."""
    ws = Workspace(test_config, base_dir=tmp_path / "work")
    ws.ensure_dirs()

    media_info = prepare_media(sample_wav, ws, test_config)

    assert media_info.duration > 0
    assert media_info.sample_rate == 16000
    assert media_info.channels == 1
