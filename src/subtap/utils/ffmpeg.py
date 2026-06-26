"""FFmpeg / FFprobe wrapper utilities."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from subtap.schemas.models import MediaInfo


def _find_binary(name: str) -> str:
    """Find ffmpeg/ffprobe binary, raise if not found."""
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(
            f"{name} not found in PATH. Install ffmpeg: brew install ffmpeg"
        )
    return path


def probe_media(file_path: Path) -> MediaInfo:
    """Run ffprobe and parse into MediaInfo."""
    ffprobe = _find_binary("ffprobe")
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Find audio stream
    audio_stream = None
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = stream
        elif stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream

    duration = float(data.get("format", {}).get("duration", 0.0))

    sample_rate = 16000
    channels = 1
    if audio_stream:
        sample_rate = int(audio_stream.get("sample_rate", 16000))
        channels = int(audio_stream.get("channels", 1))

    fps: Optional[float] = None
    if video_stream:
        r_frame_rate = video_stream.get("r_frame_rate", "")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/", 1)
            if float(den) != 0:
                fps = round(float(num) / float(den), 3)
        elif r_frame_rate:
            fps = float(r_frame_rate)

    return MediaInfo(
        duration=duration,
        sample_rate=sample_rate,
        channels=channels,
        fps=fps,
    )


def extract_audio(
    input_path: Path,
    output_path: Path,
    sample_rate: int = 16000,
    channels: int = 1,
) -> Path:
    """Extract audio from media file to mono 16kHz WAV."""
    ffmpeg = _find_binary("ffmpeg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path
