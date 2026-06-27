"""Media processing: probe + audio extraction."""

from __future__ import annotations

import json
from pathlib import Path

from subtap.schemas.config import SubtapConfig
from subtap.schemas.models import MediaInfo
from subtap.utils.ffmpeg import extract_audio, probe_media
from subtap.core.workspace import Workspace


def prepare_media(
    input_path: Path, workspace: Workspace, config: SubtapConfig
) -> MediaInfo:
    """Probe media info and extract audio to workspace.

    Steps:
    1. ffprobe -> MediaInfo
    2. Save media_info.json to workspace
    3. ffmpeg extract -> workspace/audio/source.wav
    """
    workspace.ensure_dirs()

    # Probe
    media_info = probe_media(input_path)

    # Persist media_info.json
    with open(workspace.media_info_path, "w") as f:
        json.dump(media_info.model_dump(), f, indent=2)

    # Extract audio
    extract_audio(
        input_path=input_path,
        output_path=workspace.source_audio,
        sample_rate=config.audio.sample_rate,
        channels=config.audio.channels,
    )

    return media_info
