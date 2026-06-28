"""Burn subtitle files into videos with FFmpeg."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}


def is_video(path: Path) -> bool:
    """Return whether path looks like a supported video file."""
    return path.suffix.lower() in VIDEO_EXTENSIONS


def build_burn_subtitle_command(
    video: Path,
    subtitle: Path,
    output: Path,
    *,
    ffmpeg: str = "ffmpeg",
    overwrite: bool = True,
) -> list[str]:
    """Build FFmpeg command for burning subtitles into a video."""
    vf = f"subtitles={shlex.quote(str(subtitle))}"
    command = [ffmpeg]
    command.append("-y" if overwrite else "-n")
    command.extend(["-i", str(video), "-vf", vf, "-c:v", "libx264", "-c:a", "copy", str(output)])
    return command


def run_command(command: list[str]) -> None:
    """Run FFmpeg command."""
    subprocess.run(command, check=True)


def compose_one(
    video: Path,
    subtitle: Path,
    output: Path,
    *,
    runner: Callable[[list[str]], None] | None = None,
    ffmpeg: str = "ffmpeg",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Compose one video with one subtitle file."""
    item = {
        "video": str(video),
        "subtitle": str(subtitle),
        "output": str(output),
        "status": "pending",
        "error": "",
    }
    if not is_video(video):
        item.update(status="skipped", error="不是视频文件")
        return item
    if not video.exists():
        item.update(status="failed", error="视频文件不存在")
        return item
    if not subtitle.exists():
        item.update(status="failed", error="字幕文件不存在")
        return item
    if output.exists() and not overwrite:
        item.update(status="failed", error="输出文件已存在，请使用 --overwrite")
        return item

    output.parent.mkdir(parents=True, exist_ok=True)
    runner = runner or run_command
    try:
        runner(
            build_burn_subtitle_command(
                video, subtitle, output, ffmpeg=ffmpeg, overwrite=True
            )
        )
    except Exception as exc:
        item.update(status="failed", error=str(exc))
        return item
    item.update(status="succeeded")
    return item


def compose_batch(
    items: list[dict[str, Path]],
    output_dir: Path,
    *,
    runner: Callable[[list[str]], None] = run_command,
    ffmpeg: str = "ffmpeg",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Compose many videos and write a manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for source in items:
        video = Path(source["video"])
        subtitle = Path(source["subtitle"])
        output = output_dir / f"{video.stem}_字幕版{video.suffix or '.mp4'}"
        results.append(
            compose_one(
                video,
                subtitle,
                output,
                runner=runner,
                ffmpeg=ffmpeg,
                overwrite=overwrite,
            )
        )
    manifest = {
        "ok": all(item["status"] == "succeeded" for item in results),
        "output_dir": str(output_dir),
        "items": results,
    }
    (output_dir / "compose-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
